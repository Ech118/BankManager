"""Consistency: the score, the probability, the return and the verdict must agree.

Specified by docs/verification.md.

A report can be internally contradictory while every individual number is
correct: a "strong_buy" card sitting above an expected return below the index,
or a 9/10 score next to a 35% chance of beating the market. Each number is
defensible alone; together they are incoherent, and a reader will believe the
headline rather than the table.

This is a deterministic check, so it is cheap to run on every result.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.scenario_result import Consistency, ScenarioResult
from schema.contracts.verdict import VerdictCard

VERDICT_MIN_EXCESS: dict[str, float] = {
    "strong_buy": 0.04,
    "buy": 0.01,
    "speculative_buy": 0.00,
    "hold": -0.02,
    "avoid": float("-inf"),
    "sell": float("-inf"),
}
"""Minimum expected excess return each verdict word implies.

A verdict below its floor is an error, not a matter of emphasis.
"""


def validate_consistency(scenario_result: ScenarioResult, verdict_card: VerdictCard) -> Consistency:
    """Check the four outputs tell the same story.

    Checks:
      - the verdict word against VERDICT_MIN_EXCESS,
      - scores against the excess return that produced them,
      - p_beat_sp500 against the direction of the expected return,
      - the $10,000 answer against the sign of the excess return.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
