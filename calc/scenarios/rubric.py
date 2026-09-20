"""The scoring rubric: excess return -> a 1-10 buyability score.

Specified by docs/p2/rubric.md and docs/adr/0001.

A fixed table, not a judgement. If the score were an LLM output it would drift
between runs and correlate with how the thesis was worded rather than with the
numbers. Here the same excess return always produces the same score, and any
disagreement between the score and the verdict is a bug consistency.py catches.

Never inflate. The thresholds in config.SCORE_THRESHOLDS are compressed around
the middle on purpose: the difference between a 5 and a 6 is small because our
ability to distinguish them is small.
"""

from __future__ import annotations

from calc import config
from calc._util import num
from schema.contracts.scenario_result import ScenarioResult, Scores

_HORIZONS = ("short_term", "medium_term", "long_term")


def score_for_excess(excess_return: float | None) -> int:
    """Map an excess return over the index to a 1-10 score via config.py.

    config.SCORE_THRESHOLDS is an ascending list of (upper_bound, score) pairs;
    the first pair whose upper_bound the excess return does not exceed wins,
    so the table is monotonic by construction (a better excess return can never
    produce a worse score). A missing excess return scores the neutral
    midpoint (5) rather than a confident guess in either direction.
    """
    if excess_return is None:
        return 5
    for upper, score in config.SCORE_THRESHOLDS:
        if excess_return <= upper:
            return score
    return config.SCORE_THRESHOLDS[-1][1]


def derive_scores(scenario_result: ScenarioResult) -> Scores:
    """Scores for all three horizons.

    Longer horizons carry more uncertainty, so a long-term score should not be
    more confident than the short-term one without a reason in the numbers -
    each horizon's score comes from that horizon's OWN excess_vs_sp500, so the
    scores can only diverge when the underlying numbers do.
    """
    excess = scenario_result.excess_vs_sp500
    return Scores(**{h: score_for_excess(num(getattr(excess, h))) for h in _HORIZONS})
