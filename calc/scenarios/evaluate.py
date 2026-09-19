"""Scenario evaluation and the weight-bounding algorithm.

Specified by docs/pipeline.md "Scenario weights" (amendment 1).

THE ALGORITHM, which must be implemented exactly as written because the mock
fixtures demonstrate it and the contract tests assert on it:

  1. Reject requested weights that do not sum to 1.0. A proposal that is not a
     distribution is a bug in the agent, not something to silently normalize.
  2. Clamp each weight into [default - band, default + band] from config.py.
  3. Redistribute the residual (1 - sum of clamped) across the UNCLAMPED weights
     in proportion to their size.
  4. Record one WeightClamp per scenario: requested, clamped_to, applied, plus
     `was_clamped` and `was_renormalized` flags.

Step 3 is the subtle one. Naive renormalization - scaling all three weights to
sum to 1 - would push a clamped weight straight back outside its band, undoing
step 2. Sending the residual only to the untouched weights keeps every applied
weight inside its own band.

Clamped, never rejected: an out-of-band request still contributes, it is just
bounded, and the record shows a reader exactly what the agent wanted.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Metrics
from schema.contracts.scenario_result import ScenarioResult, ScenarioWeights
from schema.contracts.scenarios import PriorShift, Scenarios


def bound_weights(requested: dict[str, float]) -> ScenarioWeights:
    """Clamp, redistribute and record. The four-step algorithm above."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def price_target(scenario: dict, factsheet: Factsheet) -> float:
    """eps_at_horizon * exit_multiple."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def annualized_return(target: float, price: float, years: int) -> float:
    """(target / price) ** (1 / years) - 1."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def evaluate_scenarios(
    scenarios: Scenarios,
    factsheet: Factsheet,
    metrics: Metrics,
    prior_shifts: list[PriorShift] | None = None,
) -> ScenarioResult:
    """The whole scenario computation.

    Expected value uses the APPLIED weights. `prior_shifts` collects every
    agent's requested tilt - the Scenario Agent's and the Red Team's - and
    prior.py caps their sum.

    Takes no `as_of`: the factsheet carries it (amendment 2).
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
