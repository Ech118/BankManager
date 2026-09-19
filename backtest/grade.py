"""Grade one backtested verdict against what actually happened (plan.txt
15.14 P2 step 7: "grader that compares to realized S&P-relative returns").
"""
from __future__ import annotations

from typing import Optional

from calc import config
from calc.value import vo_value


def grade_case(
    ticker: str,
    as_of: str,
    verdict: dict,
    realized_annualized_return: float,
    sp500_realized_return: Optional[float] = None,
) -> dict:
    """Compare the verdict's 5y prediction to what actually happened.

    realized_annualized_return: the stock's actual annualized return over the
    horizon being graded (supplied by the caller from historical prices - P2
    does not fetch market data itself, plan.txt 15.14 P2 "Do NOT: fetch data
    yourself").
    sp500_realized_return: actual S&P 500 annualized return over the same
    window; defaults to config.SP500_EXPECTED_ANNUAL_RETURN if not supplied
    (documented as an approximation, not a fetched fact).
    """
    card = verdict["card"]
    sp500 = sp500_realized_return if sp500_realized_return is not None else config.SP500_EXPECTED_ANNUAL_RETURN
    beat_sp500 = realized_annualized_return > sp500

    predicted_p = card["p_beat_sp500_5y"]
    predicted_expected = vo_value(card.get("expected_5y_return"))

    return {
        "ticker": ticker,
        "as_of": as_of,
        "verdict": card["verdict"],
        "predicted_p_beat_sp500_5y": predicted_p,
        "predicted_expected_5y_return": predicted_expected,
        "realized_annualized_return": realized_annualized_return,
        "sp500_realized_return": sp500,
        "beat_sp500": beat_sp500,
        "brier_component": (predicted_p - (1.0 if beat_sp500 else 0.0)) ** 2,
        "return_error": (
            None if predicted_expected is None else realized_annualized_return - predicted_expected
        ),
    }
