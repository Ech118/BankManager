"""P2 (Calc, Audit & Eval) owns this file. Public interface of the math layer.

Step 0 STUB: returns the ACME fixtures from fixtures/mock/. The owner replaces the
internals with real deterministic math but MUST NOT change any signature
(plan.txt 15.11). No I/O and no LLM calls belong in calc/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


def _load(name: str) -> dict:
    return json.loads((_MOCK / name).read_text())


def _require_mock(fn: str) -> None:
    if os.environ.get("BM_MODE", "mock").lower() == "live":
        raise NotImplementedError(f"calc.api.{fn}: live mode is not implemented yet (P2). Use BM_MODE=mock.")


def compute_metrics(factsheet: dict) -> dict:
    """factsheet.json -> metrics.json. Pure function."""
    _require_mock("compute_metrics")
    return _load("metrics.json")


def reverse_dcf(factsheet: dict, metrics: dict, assumptions: dict | None = None) -> dict:
    """Solve for the FCF growth the current price implies. Returns metrics.reverse_dcf
    (implied_fcf_cagr, assumptions tagged 'assumption', sensitivity_grid)."""
    _require_mock("reverse_dcf")
    return _load("metrics.json")["reverse_dcf"]


def evaluate_scenarios(scenarios: dict, factsheet: dict, metrics: dict) -> dict:
    """scenarios.json -> scenario_result.json.

    REAL implementation must: reject probabilities that do not sum to 1.0;
    compute price targets and annualized returns; start P(beat S&P) from a
    base-rate prior and apply the LLM's prior_shift only within a hard cap (C).
    """
    total = sum(s["probability"] for s in scenarios["scenarios"].values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Scenario probabilities must sum to 1.0, got {total}")
    _require_mock("evaluate_scenarios")
    return _load("scenario_result.json")


def derive_scores(scenario_result: dict) -> dict:
    """scenario_result -> {"short_term","medium_term","long_term"} ints 1..10 via a fixed rubric."""
    _require_mock("derive_scores")
    return _load("scenario_result.json")["scores"]


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Return {"ok": bool, "issues": [str]}. Score, P(beat S&P), expected return and
    verdict must agree (e.g. strong_buy with expected return below S&P is an error)."""
    _require_mock("validate_consistency")
    return {"ok": True, "issues": []}
