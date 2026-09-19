"""Unit tests for calc.scenarios (plan.txt 15.14 P2 step 3: probability
validation, price targets/returns, prior + capped shift; "Done when: ... cap
test proves the LLM cannot exceed the shift")."""
import copy
import json
from pathlib import Path

import pytest

from calc import api as calc_api
from calc import config

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def factsheet():
    return load_fixture("factsheet.json")


@pytest.fixture
def metrics(factsheet):
    return calc_api.compute_metrics(factsheet)


@pytest.fixture
def scenarios():
    return load_fixture("scenarios.json")


def test_evaluate_scenarios_matches_hand_checked_acme_values(scenarios, factsheet, metrics):
    result = calc_api.evaluate_scenarios(scenarios, factsheet, metrics)
    assert result["expected_annualized_return"]["value"] == pytest.approx(-0.019, abs=1e-3)
    assert result["p_beat_sp500"]["5y"] == pytest.approx(0.32, abs=1e-4)
    assert result["p_beat_sp500"]["3y"] == pytest.approx(0.34, abs=1e-4)
    assert result["p_beat_sp500"]["1y"] == pytest.approx(0.37, abs=1e-4)


def test_rejects_probabilities_that_do_not_sum_to_one(scenarios, factsheet, metrics):
    bad = copy.deepcopy(scenarios)
    bad["scenarios"]["base"]["probability"] = 0.9
    with pytest.raises(ValueError):
        calc_api.evaluate_scenarios(bad, factsheet, metrics)


@pytest.mark.parametrize("requested_shift", [-1.0, -0.5, -0.16, 0.16, 0.5, 1.0])
def test_prior_shift_is_hard_capped_regardless_of_llm_request(scenarios, factsheet, metrics, requested_shift):
    """error C: the LLM may request any shift; the applied shift must never
    exceed +/- config.PRIOR_SHIFT_CAP."""
    tilted = copy.deepcopy(scenarios)
    tilted["prior_shift"]["value"] = requested_shift
    result = calc_api.evaluate_scenarios(tilted, factsheet, metrics)
    applied = result["prior"]["applied_shift"]
    assert abs(applied) <= config.PRIOR_SHIFT_CAP + 1e-12
    if abs(requested_shift) > config.PRIOR_SHIFT_CAP:
        assert abs(applied) == pytest.approx(config.PRIOR_SHIFT_CAP)
    for horizon, base_rate in config.BASE_RATE_P_BEAT_SP500.items():
        expected = max(0.0, min(1.0, base_rate + applied))
        assert result["p_beat_sp500"][horizon] == pytest.approx(expected, abs=1e-4)


def test_prior_shift_within_cap_is_applied_exactly(scenarios, factsheet, metrics):
    tilted = copy.deepcopy(scenarios)
    tilted["prior_shift"]["value"] = 0.05
    result = calc_api.evaluate_scenarios(tilted, factsheet, metrics)
    assert result["prior"]["applied_shift"] == pytest.approx(0.05)


def test_p_beat_sp500_never_leaves_zero_one_even_at_extreme_shift(scenarios, factsheet, metrics):
    tilted = copy.deepcopy(scenarios)
    tilted["prior_shift"]["value"] = -1.0
    result = calc_api.evaluate_scenarios(tilted, factsheet, metrics)
    assert all(0.0 <= p <= 1.0 for p in result["p_beat_sp500"].values())


def test_derive_scores_returns_ints_one_to_ten(scenarios, factsheet, metrics):
    result = calc_api.evaluate_scenarios(scenarios, factsheet, metrics)
    scores = calc_api.derive_scores(result)
    assert set(scores) == {"short_term", "medium_term", "long_term"}
    for s in scores.values():
        assert isinstance(s, int) and 1 <= s <= 10


def test_severe_bear_case_never_scores_top_tier(scenarios, factsheet, metrics):
    """A scenario set with catastrophic downside should not get a 10 even if
    the probability-weighted expected return looks fine (uncertainty
    penalty, docs/p2/rubric.md)."""
    bullish = copy.deepcopy(scenarios)
    bullish["scenarios"]["bear"]["eps_at_horizon"]["value"] = 0.01
    bullish["scenarios"]["bear"]["exit_multiple"]["value"] = 1.0
    bullish["prior_shift"]["value"] = 0.15
    result = calc_api.evaluate_scenarios(bullish, factsheet, metrics)
    assert result["scenarios"]["bear"]["annualized_return"]["value"] <= config.SEVERE_DOWNSIDE_RETURN
    scores = calc_api.derive_scores(result)
    assert scores["short_term"] < config.SCORE_BAND_TOP
