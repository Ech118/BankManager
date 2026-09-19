"""scenarios.json -> scenario_result.json, plus the score rubric (plan.txt
15.14 P2 steps 3-4). The LLM (P3 Valuation agent) proposes scenario INPUTS and
a requested prior_shift; every probability, price target, return, P(beat S&P)
and score is computed HERE, never by the LLM (plan.txt error C).
"""
from __future__ import annotations

from typing import Optional

from calc import config
from calc.value import value, vo_value

PROBABILITY_SUM_TOLERANCE = 1e-6


def _validate_probabilities(scenarios: dict) -> None:
    total = sum(s["probability"] for s in scenarios.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise ValueError(f"Scenario probabilities must sum to 1.0, got {total}")


def _scenario_return(scenario: dict, price: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """(price_target, annualized_return) for one bear/base/bull scenario."""
    eps = vo_value(scenario.get("eps_at_horizon"))
    exit_multiple = vo_value(scenario.get("exit_multiple"))
    horizon_years = scenario.get("horizon_years")
    if eps is None or exit_multiple is None:
        return None, None
    target = eps * exit_multiple
    if price is None or price <= 0 or not horizon_years:
        return target, None
    ann = (target / price) ** (1 / horizon_years) - 1
    return target, ann


def evaluate_scenarios(scenarios: dict, factsheet: dict, metrics: dict) -> dict:
    """scenarios.json -> scenario_result.json (schema/scenario_result.json).

    Rejects probabilities that do not sum to 1 (plan.txt error C). Computes
    price targets and annualized returns per scenario, then derives
    expected_annualized_return, excess_vs_sp500 and p_beat_sp500 from a
    base-rate prior plus the LLM's prior_shift capped to +/- PRIOR_SHIFT_CAP.
    """
    scen_in = scenarios["scenarios"]
    _validate_probabilities(scen_in)

    price = vo_value(factsheet.get("market", {}).get("price"))

    scen_out = {}
    expected_return = 0.0
    have_all_returns = True
    for key, scenario in scen_in.items():
        target, ann = _scenario_return(scenario, price)
        if ann is None:
            have_all_returns = False
        else:
            expected_return += scenario["probability"] * ann
        scen_out[key] = {
            "probability": scenario["probability"],
            "price_target": value(target, "usd_per_share", "estimate",
                                   derived_from=[f"scenarios.{key}.eps_at_horizon",
                                                 f"scenarios.{key}.exit_multiple"]),
            "annualized_return": value(ann, "fraction", "estimate",
                                        derived_from=[f"scenario_result.scenarios.{key}.price_target",
                                                      "market.price"]),
        }

    expected_value = expected_return if have_all_returns else None
    sp500_expected = config.SP500_EXPECTED_ANNUAL_RETURN
    excess = None if expected_value is None else expected_value - sp500_expected

    requested_shift = scenarios["prior_shift"]["value"]
    applied_shift = max(-config.PRIOR_SHIFT_CAP, min(config.PRIOR_SHIFT_CAP, requested_shift))
    p_beat = {
        h: max(0.0, min(1.0, config.BASE_RATE_P_BEAT_SP500[h] + applied_shift))
        for h in config.BASE_RATE_P_BEAT_SP500
    }

    return {
        "schema_version": factsheet["schema_version"],
        "ticker": factsheet["ticker"],
        "as_of": factsheet["as_of"],
        "scenarios": scen_out,
        "expected_annualized_return": value(
            expected_value, "fraction", "estimate",
            derived_from=["scenario_result.scenarios.*.annualized_return"]),
        "sp500_expected_return": value(sp500_expected, "fraction", "assumption", config.SOURCE_CONFIG),
        "excess_vs_sp500": {
            h: value(excess, "fraction", "estimate",
                     derived_from=["scenario_result.expected_annualized_return",
                                   "scenario_result.sp500_expected_return"])
            for h in ("1y", "3y", "5y")
        },
        "p_beat_sp500": {h: round(p, 4) for h, p in p_beat.items()},
        "prior": {
            "base_rate": dict(config.BASE_RATE_P_BEAT_SP500),
            "requested_shift": requested_shift,
            "applied_shift": applied_shift,
            "cap": config.PRIOR_SHIFT_CAP,
        },
        "scores": derive_scores_from_excess(excess, scen_out),
        "consistency": {"ok": True, "issues": []},
    }


def _score_from_excess(excess: Optional[float]) -> int:
    """docs/p2/rubric.md is the authoritative writeup of this table."""
    if excess is None:
        return 5  # neutral/unknown midpoint; never invented as high conviction
    for upper, score in config.SCORE_BANDS:
        if excess < upper:
            return score
    return config.SCORE_BAND_TOP


def derive_scores_from_excess(excess: Optional[float], scen_out: dict) -> dict:
    bear_return = vo_value(scen_out.get("bear", {}).get("annualized_return"))
    score = _score_from_excess(excess)
    if bear_return is not None and bear_return <= config.SEVERE_DOWNSIDE_RETURN:
        score = max(1, score - config.SEVERE_DOWNSIDE_PENALTY)
    return {"short_term": score, "medium_term": score, "long_term": score}


def derive_scores(scenario_result: dict) -> dict:
    """scenario_result -> {"short_term","medium_term","long_term"} ints 1..10.

    Re-derives the same rubric from the already-computed scenario_result, for
    callers (e.g. the orchestrator) that only have scenario_result on hand.
    """
    excess = vo_value(scenario_result["excess_vs_sp500"]["5y"])
    return derive_scores_from_excess(excess, scenario_result["scenarios"])
