"""Consistency: the score, the probability, the return and the verdict must agree.

Specified by docs/verification.md.

A report can be internally contradictory while every individual number is
correct: a "strong_buy" card sitting above an expected return below the index,
or a 9/10 score next to a 35% chance of beating the market. Each number is
defensible alone; together they are incoherent, and a reader will believe the
headline rather than the table.

This is a deterministic check, so it is cheap to run on every result.

"""

from __future__ import annotations

from calc._util import num
from calc.scenarios.rubric import derive_scores
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

_DIRECTION_TOLERANCE = 0.01
"""|excess| below this is treated as flat: too small to demand a direction
from p_beat_sp500 or the $10,000 answer."""


def validate_consistency(
    scenario_result: ScenarioResult, verdict_card: VerdictCard
) -> Consistency:
    """Check the four outputs tell the same story.

    Checks:
      - the verdict word against VERDICT_MIN_EXCESS,
      - scores against the excess return that produced them,
      - p_beat_sp500 against the direction of the expected return,
      - the $10,000 answer against the sign of the excess return.
    """
    issues: list[str] = []
    excess = num(scenario_result.excess_vs_sp500.long_term)

    verdict = verdict_card.verdict
    floor = VERDICT_MIN_EXCESS.get(verdict)
    if floor is not None and excess is not None and excess < floor:
        issues.append(
            f"verdict '{verdict}' requires an expected excess return of at least "
            f"{floor:.2%}, but it is {excess:.2%}"
        )

    expected_scores = derive_scores(scenario_result)
    if scenario_result.scores.model_dump() != expected_scores.model_dump():
        issues.append(
            "scenario_result.scores does not match the rubric's output for its own "
            "excess return; scores must be recomputed, never asserted"
        )

    if excess is not None and abs(excess) > _DIRECTION_TOLERANCE:
        base_rate_lt = scenario_result.prior.base_rate.long_term
        shift = scenario_result.p_beat_sp500.long_term - base_rate_lt
        if abs(shift) > 1e-9 and (excess > 0) != (shift > 0):
            issues.append(
                f"expected excess return is {'positive' if excess > 0 else 'negative'} "
                f"({excess:.3f}) but the applied prior shift moved P(beat S&P) the "
                "opposite way"
            )

        choice = verdict_card.ten_thousand_dollar_answer.choice
        if excess > 0 and choice != "this_stock":
            issues.append(
                f"expected excess return is positive ({excess:.3f}) but the $10,000 "
                "answer chose the S&P 500"
            )
        elif excess < 0 and choice != "sp500":
            issues.append(
                f"expected excess return is negative ({excess:.3f}) but the $10,000 "
                "answer chose this stock"
            )

    return Consistency(ok=not issues, issues=issues)
