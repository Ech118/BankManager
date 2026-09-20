"""evaluate_scenarios, derive_scores, validate_consistency.

These are the tests that stop an agent writing its own probabilities (error C,
amendment 1), so they are the ones to read first: the weight band, the prior cap,
and the fact that neither can be bypassed by wording.
"""

from __future__ import annotations

import pytest

from calc import config
from calc.api import derive_scores, evaluate_scenarios, validate_consistency
from calc.scenarios.evaluate import bound_weights
from calc.scenarios.prior import apply_shifts, p_beat_sp500
from calc.scenarios.rubric import score_for_excess
from calc.tests.support import load_mock
from schema.contracts.scenario_result import ScenarioResult, ScenarioWeights


@pytest.fixture
def scenarios() -> dict:
    return load_mock("scenarios.json")


@pytest.fixture
def metrics() -> dict:
    return load_mock("metrics.json")


@pytest.fixture
def pinned_result() -> dict:
    return load_mock("scenario_result.json")


@pytest.fixture
def card() -> dict:
    return load_mock("verdict.json")["card"]


# --------------------------------------------------------------------------
# The pinned ACME result
# --------------------------------------------------------------------------
def test_acme_expected_return_is_minus_1_9_percent(acme, scenarios, metrics):
    """The number the roadmap pins: about -1.9%/yr against the index's 7%."""
    result = evaluate_scenarios(scenarios, acme, metrics)
    assert result["expected_annualized_return"]["value"] == pytest.approx(-0.0194506576)
    assert result["sp500_expected_return"]["value"] == 0.07
    assert result["excess_vs_sp500"]["long_term"]["value"] == pytest.approx(-0.0894506576)


def test_every_pinned_scenario_number_matches(acme, scenarios, metrics, pinned_result):
    result = evaluate_scenarios(scenarios, acme, metrics)
    for name in ("bear", "base", "bull"):
        want = pinned_result["scenarios"][name]
        got = result["scenarios"][name]
        assert got["probability"] == pytest.approx(want["probability"])
        assert got["price_target"]["value"] == pytest.approx(
            want["price_target"]["value"], rel=1e-9
        )
        assert got["annualized_return"]["value"] == pytest.approx(
            want["annualized_return"]["value"], rel=1e-9
        )
    assert result["p_beat_sp500"] == pinned_result["p_beat_sp500"]
    assert result["scores"] == pinned_result["scores"]
    assert result["prior"]["applied_shift"] == pinned_result["prior"]["applied_shift"]
    assert result["prior"]["shift_reasons"] == pinned_result["prior"]["shift_reasons"]


def test_result_is_contract_valid(acme, scenarios, metrics):
    ScenarioResult.model_validate(evaluate_scenarios(scenarios, acme, metrics))


def test_probabilities_must_sum_to_one(acme, scenarios, metrics):
    """A proposal that is not a distribution is an agent bug, not something to fix."""
    scenarios["scenarios"]["base"]["probability"] = 0.9
    with pytest.raises(ValueError, match="sum to 1.0"):
        evaluate_scenarios(scenarios, acme, metrics)


# --------------------------------------------------------------------------
# eps_at_horizon: the decision P3 was blocked on
# --------------------------------------------------------------------------
def test_eps_at_horizon_is_derived_from_the_factsheet(acme, scenarios, metrics):
    """5e9 x 1.03^5 x 0.10 / 395e6 = 1.4674355371, the fixture's bear figure."""
    result = evaluate_scenarios(scenarios, acme, metrics)
    eps = result["scenarios"]["bear"]["eps_at_horizon"]
    assert eps["value"] == pytest.approx(5e9 * 1.03**5 * 0.10 / 395e6)
    assert eps["type"] == "estimate"
    assert "market.shares_outstanding" in eps["derived_from"]
    assert "financials.FY2025.revenue" in eps["derived_from"]


def test_eps_uses_current_shares_not_the_diluted_average(acme, scenarios, metrics):
    """ACME's cover-page count is 395M; FY2025's diluted average is 400M."""
    result = evaluate_scenarios(scenarios, acme, metrics)
    eps = result["scenarios"]["base"]["eps_at_horizon"]["value"]
    assert eps == pytest.approx(5e9 * 1.08**5 * 0.125 / 395_000_000)
    assert eps != pytest.approx(5e9 * 1.08**5 * 0.125 / 400_000_000)


def test_agent_supplied_eps_is_recomputed_not_trusted(acme, scenarios, metrics):
    """A model that fills the field does not get to move the price target."""
    scenarios["scenarios"]["bull"]["eps_at_horizon"]["value"] = 99.0
    scenarios["scenarios"]["bull"]["eps_at_horizon"]["status"] = "ok"
    result = evaluate_scenarios(scenarios, acme, metrics)
    eps = result["scenarios"]["bull"]["eps_at_horizon"]
    assert eps["value"] == pytest.approx(3.1231371601), "calc/ recomputes"
    assert eps["agent_supplied"] == 99.0, "and keeps the disagreement visible"
    assert "recomputed" in eps["note"]
    assert result["scenarios"]["bull"]["price_target"]["value"] == pytest.approx(
        3.1231371601 * 26.0
    )


def test_unavailable_input_excludes_the_scenario_with_a_reason(acme, scenarios, metrics):
    """A scenario with no derivable EPS keeps its weight but leaves the average."""
    scenarios["scenarios"]["bear"]["terminal_margin"] = {
        "value": None,
        "unit": "fraction",
        "type": "assumption",
        "status": "unavailable",
    }
    result = evaluate_scenarios(scenarios, acme, metrics)
    bear = result["scenarios"]["bear"]
    assert bear["eps_at_horizon"]["value"] is None
    assert "terminal_margin" in bear["eps_at_horizon"]["unavailable_reason"]
    assert bear["price_target"]["value"] is None
    assert bear["probability"] == 0.3, "the weight is not silently removed"
    assert any("bear" in note for note in result["excluded_scenarios"])
    # The expected value is the base/bull blend, renormalized over 70% of weight.
    assert result["expected_annualized_return"]["value"] == pytest.approx(0.0323462653)
    assert any("renormalized" in note for note in result["excluded_scenarios"])


def test_no_scenario_at_all_is_unavailable_not_zero(acme, scenarios, metrics):
    del acme["market"]["shares_outstanding"]
    result = evaluate_scenarios(scenarios, acme, metrics)
    assert result["expected_annualized_return"]["value"] is None
    assert result["expected_annualized_return"]["status"] == "unavailable"
    assert result["scores"] == {"short_term": 5, "medium_term": 5, "long_term": 5}


# --------------------------------------------------------------------------
# The weight band (amendment 1)
# --------------------------------------------------------------------------
def test_out_of_band_weight_is_clamped_not_rejected():
    """bear=0.55 with default 0.30 and band 0.15 clamps to 0.45."""
    weights = bound_weights({"bear": 0.55, "base": 0.30, "bull": 0.15})
    ScenarioWeights.model_validate(weights)
    assert weights["bear"] == pytest.approx(0.45)
    assert weights["bear"] + weights["base"] + weights["bull"] == pytest.approx(1.0)
    assert weights["any_clamped"] is True and weights["renormalized"] is True


def test_clamped_result_matches_the_worked_example():
    """docs/pipeline.md's table, and fixtures/mock/scenario_weights_clamped.json."""
    fixture = load_mock("scenario_weights_clamped.json")
    weights = bound_weights({"bear": 0.55, "base": 0.30, "bull": 0.15})
    for name in ("bear", "base", "bull"):
        assert weights[name] == pytest.approx(fixture[name]), name
    got = {clamp["scenario"]: clamp for clamp in weights["clamps"]}
    for clamp in fixture["clamps"]:
        mine = got[clamp["scenario"]]
        for field in ("requested", "clamped_to", "applied", "default_weight", "band"):
            assert mine[field] == pytest.approx(clamp[field]), f"{clamp['scenario']}.{field}"
        assert mine["was_clamped"] == clamp["was_clamped"]
        assert mine["was_renormalized"] == clamp["was_renormalized"]


def test_redistribution_keeps_every_weight_inside_its_band():
    """Naive renormalization would push the clamped weight straight back out."""
    band = config.SCENARIO_WEIGHT_BAND
    for requested in (
        {"bear": 0.55, "base": 0.30, "bull": 0.15},
        {"bear": 0.05, "base": 0.60, "bull": 0.35},
        {"bear": 0.70, "base": 0.20, "bull": 0.10},
        {"bear": 0.00, "base": 1.00, "bull": 0.00},
        {"bear": 1.00, "base": 0.00, "bull": 0.00},
        {"bear": 0.34, "base": 0.33, "bull": 0.33},
    ):
        weights = bound_weights(requested)
        ScenarioWeights.model_validate(weights)
        for clamp in weights["clamps"]:
            low = clamp["default_weight"] - band
            high = clamp["default_weight"] + band
            assert low - 1e-9 <= clamp["applied"] <= high + 1e-9, (requested, clamp["scenario"])
        assert sum(weights[n] for n in ("bear", "base", "bull")) == pytest.approx(1.0)


def test_every_weight_is_recorded_never_silently_dropped():
    weights = bound_weights({"bear": 0.55, "base": 0.30, "bull": 0.15})
    assert sorted(clamp["scenario"] for clamp in weights["clamps"]) == ["base", "bear", "bull"]


def test_a_clamp_cannot_be_silent():
    """The contract rejects flags that disagree with the numbers; so must we."""
    weights = bound_weights(
        {"bear": 0.55, "base": 0.30, "bull": 0.15},
        {"bear": "competitor bundling is already visible in the risk disclosure"},
    )
    bear = next(c for c in weights["clamps"] if c["scenario"] == "bear")
    assert bear["requested"] == 0.55 and bear["clamped_to"] == pytest.approx(0.45)
    assert bear["was_clamped"] is True
    assert bear["reason"], "the agent's own rationale is carried through"


def test_applied_weights_are_the_ones_used_for_expected_value(acme, scenarios, metrics):
    scenarios["scenarios"]["bear"]["probability"] = 0.55
    scenarios["scenarios"]["base"]["probability"] = 0.30
    scenarios["scenarios"]["bull"]["probability"] = 0.15
    result = evaluate_scenarios(scenarios, acme, metrics)
    weights = result["weights"]
    expected = sum(
        result["scenarios"][name]["annualized_return"]["value"] * weights[name]
        for name in ("bear", "base", "bull")
    )
    assert result["expected_annualized_return"]["value"] == pytest.approx(expected)
    assert weights["bear"] == pytest.approx(0.45), "the request was 0.55"


# --------------------------------------------------------------------------
# The prior cap (error C)
# --------------------------------------------------------------------------
def test_prior_shift_respects_cap():
    """The contract-suite test, held at the source rather than in a fixture."""
    prior = apply_shifts([{"value": -0.40, "reason": "very bearish", "source": "red_team"}])
    assert abs(prior["applied_shift"]) <= prior["cap"] + 1e-12
    assert abs(prior["applied_shift"]) <= abs(prior["requested_shift"]) + 1e-12
    assert prior["applied_shift"] == pytest.approx(-config.PRIOR_SHIFT_CAP)
    assert prior["cap_applied"] is True and "hard cap" in prior["cap_note"]


def test_shifts_are_summed_before_the_cap():
    """Two agents must not exceed the cap by splitting a request."""
    prior = apply_shifts(
        [
            {"value": -0.10, "reason": "premium to peers", "source": "scenario"},
            {"value": -0.12, "reason": "channel risk", "source": "red_team"},
        ]
    )
    assert prior["requested_shift"] == pytest.approx(-0.22)
    assert prior["applied_shift"] == pytest.approx(-0.15)
    assert len(prior["shift_reasons"]) == 2


def test_code_may_shrink_a_request_never_enlarge_it():
    prior = apply_shifts([{"value": 0.03, "reason": "durable moat", "source": "scenario"}])
    assert prior["applied_shift"] == pytest.approx(0.03), "inside the cap, applied whole"


def test_an_unreasoned_shift_is_dropped():
    """The reason IS the argument; without one there is nothing to weigh."""
    prior = apply_shifts([{"value": -0.10, "reason": "  ", "source": "red_team"}])
    assert prior["requested_shift"] == 0.0 and prior["applied_shift"] == 0.0
    assert prior["dropped_shifts"] and "red_team" in prior["dropped_shifts"][0]


def test_p_beat_is_the_base_rate_plus_the_applied_shift():
    prior = apply_shifts([{"value": -0.10, "reason": "expensive", "source": "scenario"}])
    assert p_beat_sp500(prior) == {"short_term": 0.37, "medium_term": 0.34, "long_term": 0.32}


def test_p_beat_is_clipped_to_a_probability():
    prior = apply_shifts([{"value": -0.99, "reason": "collapse", "source": "red_team"}])
    beats = p_beat_sp500(prior)
    assert all(0.0 <= value <= 1.0 for value in beats.values())
    assert beats["long_term"] == pytest.approx(0.27), "0.42 - 0.15, the cap"


def test_explicit_prior_shifts_replace_the_embedded_one(acme, scenarios, metrics):
    """P3's list already contains the Scenario Agent's shift; counting both doubles it."""
    result = evaluate_scenarios(
        scenarios,
        acme,
        metrics,
        [
            {"value": -0.10, "reason": "premium to peers", "source": "scenario"},
            {"value": -0.03, "reason": "bundling risk", "source": "red_team"},
        ],
    )
    assert result["prior"]["requested_shift"] == pytest.approx(-0.13)
    assert len(result["prior"]["shift_reasons"]) == 2


# --------------------------------------------------------------------------
# Per-horizon output
# --------------------------------------------------------------------------
def test_each_horizon_carries_a_value_per_scenario(acme, scenarios, metrics):
    result = evaluate_scenarios(scenarios, acme, metrics)
    bear = result["scenarios"]["bear"]["by_horizon"]
    assert set(bear) == {"short_term", "medium_term", "long_term"}
    annual = result["scenarios"]["bear"]["annualized_return"]["value"]
    assert bear["short_term"]["value_per_share"]["value"] == pytest.approx(50.0 * (1 + annual))
    assert bear["long_term"]["value_per_share"]["value"] == pytest.approx(50.0 * (1 + annual) ** 5)
    # The annualized figure is horizon-invariant by construction; the cumulative
    # one is what differs, and it is the honest way to show a five-year bear case.
    assert bear["long_term"]["annualized_return"]["value"] == pytest.approx(annual)
    assert bear["long_term"]["cumulative_return"]["value"] == pytest.approx((1 + annual) ** 5 - 1)
    assert bear["long_term"]["cumulative_return"]["value"] < -0.5


def test_a_shorter_scenario_horizon_is_marked_extrapolated(acme, scenarios, metrics):
    for case in scenarios["scenarios"].values():
        case["horizon_years"] = 3
    result = evaluate_scenarios(scenarios, acme, metrics)
    by_horizon = result["scenarios"]["base"]["by_horizon"]
    assert by_horizon["medium_term"].get("extrapolated") is None
    assert by_horizon["long_term"]["extrapolated"] is True
    assert "same rate continues" in by_horizon["long_term"]["note"]


def test_sp500_return_comes_from_the_factsheet_when_published(acme, scenarios, metrics):
    acme["sp500_baseline"]["expected_return"] = {
        "value": 0.065,
        "unit": "fraction",
        "type": "assumption",
        "status": "ok",
        "source_id": "src:config:sp500_baseline:2026.09",
    }
    result = evaluate_scenarios(scenarios, acme, metrics)
    assert result["sp500_expected_return"]["value"] == 0.065
    assert result["sp500_expected_return"]["basis"] == "factsheet"
    assert result["excess_vs_sp500"]["short_term"]["value"] == pytest.approx(-0.0844506576)


def test_the_factsheet_baseline_is_echoed_beside_the_assumption(acme, scenarios, metrics):
    result = evaluate_scenarios(scenarios, acme, metrics)
    index = result["sp500_expected_return"]
    assert index["basis"] == "config"
    assert index["baseline"]["forward_pe"]["value"] == 22.0
    assert index["baseline"]["risk_free_rate"]["value"] == 0.043


# --------------------------------------------------------------------------
# Sensitivity
# --------------------------------------------------------------------------
def test_acme_verdict_does_not_depend_on_the_bear_case(acme, scenarios, metrics):
    """The flip point is a NEGATIVE bear weight, which is the finding."""
    sensitivity = evaluate_scenarios(scenarios, acme, metrics)["sensitivity"]
    assert sensitivity["flips_at_bear_probability"] == pytest.approx(-0.2180847776)
    assert sensitivity["reachable"] is False
    assert "with the bear case at 0%" in sensitivity["reason"].lower()


def test_a_reachable_flip_is_reported_with_its_band(acme, scenarios, metrics):
    """Make the base and bull cases good enough that the bear weight decides."""
    scenarios["scenarios"]["base"]["revenue_cagr"]["value"] = 0.20
    scenarios["scenarios"]["bull"]["revenue_cagr"]["value"] = 0.25
    result = evaluate_scenarios(scenarios, acme, metrics)
    sensitivity = result["sensitivity"]
    assert 0.0 <= sensitivity["flips_at_bear_probability"] <= 1.0
    assert sensitivity["reachable"] is True
    assert sensitivity["allowed_band"] == [0.15, 0.45]
    # Solving it back: at the flip weight the expected return equals the index.
    flip = sensitivity["flips_at_bear_probability"]
    rest = sensitivity["base_bull_blend"]
    assert flip * sensitivity["bear_return"] + (1 - flip) * rest == pytest.approx(0.07)


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------
def test_score_bands(acme, scenarios, metrics):
    assert score_for_excess(-0.20, "short_term") == 3
    assert score_for_excess(-0.03, "short_term") == 4
    assert score_for_excess(0.0, "short_term") == 5
    assert score_for_excess(0.03, "short_term") == 6
    assert score_for_excess(0.50, "short_term") == 7
    assert score_for_excess(None) == 5, "not knowing is not evidence"


def test_longer_horizons_are_pulled_toward_neutral():
    assert score_for_excess(-0.0894506576, "short_term") == 3
    assert score_for_excess(-0.0894506576, "medium_term") == 3
    assert score_for_excess(-0.0894506576, "long_term") == 4
    assert score_for_excess(0.09, "short_term") == 7
    assert score_for_excess(0.09, "long_term") == 6


def test_severe_downside_costs_a_point(acme, scenarios, metrics):
    result = evaluate_scenarios(scenarios, acme, metrics)
    before = derive_scores(result)
    result["scenarios"]["bear"]["annualized_return"]["value"] = -0.30
    after = derive_scores(result)
    assert all(after[h] == max(1, before[h] - 1) for h in before)


def test_scores_are_never_inflated_past_the_table(acme, scenarios, metrics):
    result = evaluate_scenarios(scenarios, acme, metrics)
    for horizon in result["excess_vs_sp500"]:
        result["excess_vs_sp500"][horizon]["value"] = 5.0
    assert derive_scores(result) == {"short_term": 7, "medium_term": 7, "long_term": 7}


# --------------------------------------------------------------------------
# Consistency
# --------------------------------------------------------------------------
def test_the_pinned_acme_card_is_consistent(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    assert validate_consistency(result, card) == {"ok": True, "issues": []}


def test_a_bullish_verdict_below_the_index_is_an_error(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    card = {**card, "verdict": "strong_buy"}
    report = validate_consistency(result, card)
    assert report["ok"] is False
    assert any("strong_buy" in issue for issue in report["issues"])
    assert any("trails the S&P assumption" in issue for issue in report["issues"])


def test_a_bearish_verdict_above_the_tolerance_is_an_error(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    for horizon in result["excess_vs_sp500"]:
        result["excess_vs_sp500"][horizon]["value"] = 0.09
    result["scores"] = derive_scores(result)
    report = validate_consistency(result, {**card, "verdict": "avoid", "scores": result["scores"]})
    assert report["ok"] is False
    assert any("bearish" in issue for issue in report["issues"])


def test_a_hand_edited_score_is_caught(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    report = validate_consistency(result, {**card, "scores": {**card["scores"], "long_term": 9}})
    assert report["ok"] is False
    assert any("long_term score is 9" in issue for issue in report["issues"])


def test_a_copied_card_number_that_drifted_is_caught(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    report = validate_consistency(result, {**card, "p_beat_sp500_5y": 0.61})
    assert report["ok"] is False
    assert any("p_beat_sp500_5y" in issue for issue in report["issues"])


def test_the_ten_thousand_dollar_answer_must_match_the_sign(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    card = {**card, "ten_thousand_dollar_answer": {"choice": "this_stock", "reason": "vibes"}}
    report = validate_consistency(result, card)
    assert report["ok"] is False
    assert any("$10,000" in issue for issue in report["issues"])


def test_a_prior_shifted_against_the_numbers_is_caught(acme, scenarios, metrics, card):
    result = evaluate_scenarios(scenarios, acme, metrics)
    result["p_beat_sp500"]["long_term"] = 0.55
    report = validate_consistency(result, {**card, "p_beat_sp500_5y": 0.55})
    assert report["ok"] is False
    assert any("shifted UP" in issue for issue in report["issues"])


def test_ok_and_issues_cannot_disagree(acme, scenarios, metrics, card):
    """The Consistency model rejects ok=True with issues, so this cannot drift."""
    from schema.contracts.scenario_result import Consistency

    report = validate_consistency(evaluate_scenarios(scenarios, acme, metrics), card)
    Consistency.model_validate(report)
    with pytest.raises(ValueError):
        Consistency.model_validate({"ok": True, "issues": ["something"]})
