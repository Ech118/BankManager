"""P2 (Calc, Audit & Eval) owns this file. Public interface of the math layer.

Real deterministic math (plan.txt 15.14 P2). No I/O and no LLM calls belong
in calc/ - every function here is a pure function of its arguments, so it
does not depend on BM_MODE at all (that only governs how P1 fetched the
factsheet in the first place). Signatures MUST NOT change (plan.txt 15.11);
tests/contracts/test_signatures.py enforces this.
"""
from __future__ import annotations

from calc.consistency import validate_consistency as _validate_consistency
from calc.dcf import compute_reverse_dcf
from calc.metrics import compute_metrics as _compute_metrics
from calc.scenarios import derive_scores as _derive_scores
from calc.scenarios import evaluate_scenarios as _evaluate_scenarios
from calc.value import vo_value


def compute_metrics(factsheet: dict) -> dict:
    """factsheet.json -> metrics.json. Pure function."""
    return _compute_metrics(factsheet)


def reverse_dcf(factsheet: dict, metrics: dict, assumptions: dict | None = None) -> dict:
    """Solve for the FCF growth the current price implies. Returns metrics.reverse_dcf
    (implied_fcf_cagr, assumptions tagged 'assumption', sensitivity_grid)."""
    enterprise_value = vo_value(factsheet.get("market", {}).get("enterprise_value"))
    fcf = vo_value(metrics.get("cash_flow", {}).get("fcf"))
    return compute_reverse_dcf(enterprise_value, fcf, assumptions)


def evaluate_scenarios(scenarios: dict, factsheet: dict, metrics: dict) -> dict:
    """scenarios.json -> scenario_result.json.

    Rejects probabilities that do not sum to 1.0; computes price targets and
    annualized returns; starts P(beat S&P) from a base-rate prior and applies
    the LLM's prior_shift only within a hard cap (error C)."""
    return _evaluate_scenarios(scenarios, factsheet, metrics)


def derive_scores(scenario_result: dict) -> dict:
    """scenario_result -> {"short_term","medium_term","long_term"} ints 1..10 via a fixed rubric."""
    return _derive_scores(scenario_result)


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Return {"ok": bool, "issues": [str]}. Score, P(beat S&P), expected return and
    verdict must agree (e.g. strong_buy with expected return below S&P is an error)."""
    return _validate_consistency(scenario_result, verdict_card)
