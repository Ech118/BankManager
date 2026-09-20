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
from calc.value import vo_value


def score_for_excess(excess_return: float | None, horizon: str = "short_term") -> int:
    """Map an excess return over the index to a 1-10 score via config.py.

    Two things happen here, both in config.py so a reader can audit them:

    1. the excess is DIVIDED by `SCORE_HORIZON_UNCERTAINTY[horizon]`, which pulls
       longer horizons toward neutral - a five-year call is a weaker claim than a
       twelve-month one, and the score should say so rather than repeating the
       same confident number three times;
    2. the result is looked up in `SCORE_THRESHOLDS`, an upper-bound table.

    An unavailable excess scores `SCORE_NEUTRAL`, never 1 and never 10: not
    knowing is not evidence in either direction.
    """
    if excess_return is None:
        return config.SCORE_NEUTRAL
    uncertainty = config.SCORE_HORIZON_UNCERTAINTY.get(horizon, 1.0)
    effective = excess_return / uncertainty if uncertainty else excess_return
    for upper, score in config.SCORE_THRESHOLDS:
        if effective <= upper:
            return score
    return config.SCORE_THRESHOLDS[-1][1]


def derive_scores(scenario_result: dict) -> dict:
    """Scores for all three horizons.

    Longer horizons carry more uncertainty, so a long-term score should not be
    more confident than the short-term one without a reason in the numbers.

    The severe-downside penalty is the second half: a stock with a plausible
    -25%/yr bear path never reads as a high score purely because the bull case is
    doing the lifting in the weighted average.
    """
    excess = (
        scenario_result.get("excess_vs_sp500")
        or scenario_result.get("expected_return_vs_sp500")
        or {}
    )
    bear = ((scenario_result.get("scenarios") or {}).get("bear") or {}).get("annualized_return")
    penalty = (
        config.SEVERE_DOWNSIDE_PENALTY
        if (vo_value(bear) is not None and vo_value(bear) <= config.SEVERE_DOWNSIDE_RETURN)
        else 0
    )
    scores = {}
    for horizon in ("short_term", "medium_term", "long_term"):
        raw = score_for_excess(vo_value(excess.get(horizon)), horizon)
        scores[horizon] = max(config.SCORE_FLOOR, min(config.SCORE_CEILING, raw - penalty))
    return scores
