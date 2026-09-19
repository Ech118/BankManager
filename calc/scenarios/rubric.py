"""The scoring rubric: excess return -> a 1-10 buyability score.

Specified by docs/p2/rubric.md and docs/adr/0001.

A fixed table, not a judgement. If the score were an LLM output it would drift
between runs and correlate with how the thesis was worded rather than with the
numbers. Here the same excess return always produces the same score, and any
disagreement between the score and the verdict is a bug consistency.py catches.

Never inflate. The thresholds in config.SCORE_THRESHOLDS are compressed around
the middle on purpose: the difference between a 5 and a 6 is small because our
ability to distinguish them is small.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.scenario_result import ScenarioResult, Scores


def score_for_excess(excess_return: float) -> int:
    """Map an excess return over the index to a 1-10 score via config.py."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def derive_scores(scenario_result: ScenarioResult) -> Scores:
    """Scores for all three horizons.

    Longer horizons carry more uncertainty, so a long-term score should not be
    more confident than the short-term one without a reason in the numbers.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
