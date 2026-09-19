"""P2 (Calc, Audit & Eval) owns this file. Public interface of the math layer.

Step 0 STUB: returns the ACME fixtures from fixtures/mock/. The owner replaces
the internals with real deterministic math but MUST NOT change any signature
(CONTRACT-CHANGE PR, CONTRIBUTING.md).

calc/ IS PURE (docs/adr/0001, docs/adr/0007):
  - no network, no database, no filesystem beyond the mock fixtures,
  - no LLM call, ever,
  - no `as_of` parameter where a factsheet is already supplied: the factsheet's
    own as_of is authoritative and a second one could silently disagree.

Everything an LLM proposes is BOUNDED here, and the bounding is recorded:
  - scenario weights are clamped into a band around the defaults (ScenarioWeights),
  - the prior shift is capped (Prior).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


def _load(name: str) -> Any:
    return json.loads((_MOCK / name).read_text(encoding="utf-8"))


def _mode() -> str:
    return os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()


def _require_mock(fn: str) -> None:
    if _mode() == "live":
        raise NotImplementedError(
            f"calc.api.{fn}: live mode is not implemented yet (P2, roadmap Step 2). Use MODE=mock."
        )


def compute_metrics(factsheet: dict) -> dict:
    """Factsheet -> Metrics. Pure function.

    Takes no `as_of`: `factsheet["as_of"]` is authoritative for the whole run.
    """
    _require_mock("compute_metrics")
    return _load("metrics.json")


def reverse_dcf(factsheet: dict, metrics: dict, assumptions: dict | None = None) -> dict:
    """Solve for the FCF growth the current price implies.

    ALWAYS returns a sensitivity grid: a single point answer hides how much the
    result depends on the discount rate (error D).
    """
    _require_mock("reverse_dcf")
    return _load("metrics.json")["reverse_dcf"]


def calculate_valuation(request: dict) -> dict:
    """The MCP-exposed valuation entry point (CalculateValuationRequest/Response).

    mcp_server/tools/calculate_valuation.py is a thin wrapper over this function
    and holds no formulas of its own. That wrapper is the ONE sanctioned
    cross-partition import in the repo (docs/adr/0007).
    """
    _require_mock("calculate_valuation")
    metrics = _load("metrics.json")
    return {
        "metrics": metrics,
        "reverse_dcf": metrics["reverse_dcf"],
        "notes": ["Mock valuation: ACME fixtures, no computation performed."],
        "as_of": metrics["as_of"],
        "truncated": False,
    }


def evaluate_scenarios(
    scenarios: dict, factsheet: dict, metrics: dict, prior_shifts: list[dict] | None = None
) -> dict:
    """Scenarios -> ScenarioResult. Where every probability in the product is decided.

    The REAL implementation must:
      1. reject requested weights that do not sum to 1.0;
      2. clamp each weight into [default - band, default + band] and redistribute
         the residual across the UNCLAMPED weights in proportion, so no applied
         weight is pushed back outside its band;
      3. record every clamp in ScenarioWeights - a weight may never be silently
         altered or dropped;
      4. compute price targets and annualized returns per scenario;
      5. start P(beat S&P) from the base-rate prior and apply the SUM of
         `prior_shifts` (Scenario Agent plus Red Team) only within the hard cap,
         recording requested vs applied (error C).

    `prior_shifts` is a list of PriorShift dicts. None means use only
    `scenarios["prior_shift"]`.

    Takes no `as_of`: the factsheet carries it.
    """
    total = sum(s["probability"] for s in scenarios["scenarios"].values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Scenario probabilities must sum to 1.0, got {total}")
    _require_mock("evaluate_scenarios")
    return _load("scenario_result.json")


def derive_scores(scenario_result: dict) -> dict:
    """ScenarioResult -> {short_term, medium_term, long_term} ints 1..10.

    A fixed rubric mapping excess return to a score. Documented in
    docs/p2/rubric.md. Never inflated, and never produced by an LLM.
    """
    _require_mock("derive_scores")
    return _load("scenario_result.json")["scores"]


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Return {"ok": bool, "issues": [str]}.

    Score, P(beat S&P), expected return and the verdict enum must agree. A
    "strong_buy" whose expected return trails the index is an error, not a
    matter of taste.
    """
    _require_mock("validate_consistency")
    return {"ok": True, "issues": []}
