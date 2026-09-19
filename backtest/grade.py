"""Grade past predictions against realized S&P-relative returns.

Specified by docs/roadmap.md Step 6.

The measure is EXCESS return over the index, not absolute return. A prediction
that a stock rose 15% in a year the index rose 25% was wrong, and an absolute
measure would score it as a success.

TODO(roadmap Step 6, P2).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker


def realized_excess_return(
    ticker: Ticker, start: ISODate, end: ISODate
) -> float | None:
    """Total return minus the index's, over the same window.

    None when the window is incomplete - a partial period must not be graded as
    if it had finished.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def grade(prediction: dict, realized: float) -> dict:
    """Score one prediction. Records the predicted probability and the outcome,
    which is what the calibration chart needs."""
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def brier_score(predictions: list[tuple[float, bool]]) -> float:
    """Mean squared error of probabilistic predictions.

    The right summary statistic here: it rewards being both accurate and
    appropriately uncertain, and punishes confident wrong answers hardest.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")
