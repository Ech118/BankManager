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

from calc import config
from calc.scenarios.rubric import derive_scores
from calc.value import vo_value

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

BULLISH = ("strong_buy", "buy", "speculative_buy")
BEARISH = ("sell", "avoid")

BEARISH_MAX_EXCESS = 0.05
"""A bearish word above this much expected excess return is a contradiction.

P3's stand-in applies the same number (their 2026-09-20 request), so the two
sides of the gate agree on where the line is.
"""


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Check the four outputs tell the same story.

    Checks:
      - the verdict word against VERDICT_MIN_EXCESS,
      - the bullish/bearish rules P3 applies in its own stand-in,
      - scores against the excess return that produced them,
      - the copied card numbers against their source in ScenarioResult,
      - p_beat_sp500 against the direction of the expected return,
      - the $10,000 answer against the sign of the excess return.
    """
    issues: list[str] = []
    verdict = (verdict_card or {}).get("verdict")
    expected = vo_value(scenario_result.get("expected_annualized_return") or {})
    index = vo_value(scenario_result.get("sp500_expected_return") or {})
    excess_block = (
        scenario_result.get("excess_vs_sp500")
        or scenario_result.get("expected_return_vs_sp500")
        or {}
    )
    long_excess = vo_value(excess_block.get("long_term"))

    # --- the verdict word -------------------------------------------------
    if verdict not in VERDICT_MIN_EXCESS:
        issues.append(f"verdict {verdict!r} is not one of {sorted(VERDICT_MIN_EXCESS)}")
    elif long_excess is not None:
        floor = VERDICT_MIN_EXCESS[verdict]
        if long_excess < floor:
            issues.append(
                f"verdict {verdict!r} implies an expected excess return of at least "
                f"{floor:+.1%}/yr, but the long-term excess is {long_excess:+.1%}/yr"
            )
        if verdict in BULLISH and expected is not None and index is not None and expected < index:
            issues.append(
                f"verdict {verdict!r} is bullish, but the expected return "
                f"({expected:.1%}/yr) trails the S&P assumption ({index:.1%}/yr)"
            )
        if verdict in BEARISH and long_excess > BEARISH_MAX_EXCESS:
            issues.append(
                f"verdict {verdict!r} is bearish, but the long-term excess return is "
                f"{long_excess:+.1%}/yr, above the {BEARISH_MAX_EXCESS:+.0%} tolerance"
            )

    # --- the scores -------------------------------------------------------
    recomputed = derive_scores(scenario_result)
    for source, label in (
        (scenario_result.get("scores"), "scenario_result"),
        ((verdict_card or {}).get("scores"), "verdict card"),
    ):
        if not source:
            continue
        for horizon, expected_score in recomputed.items():
            got = source.get(horizon)
            if got is not None and got != expected_score:
                issues.append(
                    f"the {label}'s {horizon} score is {got}, but the rubric gives "
                    f"{expected_score} for that excess return"
                )

    # --- numbers code copies ---------------------------------------------
    p_beat = scenario_result.get("p_beat_sp500") or {}
    card_p = (verdict_card or {}).get("p_beat_sp500_5y")
    if card_p is not None and p_beat.get("long_term") is not None:
        if abs(card_p - p_beat["long_term"]) > 1e-9:
            issues.append(
                f"card p_beat_sp500_5y {card_p} does not equal p_beat_sp500.long_term "
                f"{p_beat['long_term']}"
            )
    card_return = vo_value((verdict_card or {}).get("expected_5y_return") or {})
    if card_return is not None and expected is not None and abs(card_return - expected) > 1e-9:
        issues.append(
            f"card expected_5y_return {card_return} does not equal "
            f"expected_annualized_return {expected}"
        )

    # --- the prior against the direction of the return --------------------
    base = config.BASE_RATE_P_BEAT_SP500["long_term"]
    long_p = p_beat.get("long_term")
    if long_p is not None and long_excess is not None:
        if long_excess > 0.02 and long_p < base - 1e-9:
            issues.append(
                f"the expected return beats the index by {long_excess:+.1%}/yr, but "
                f"P(beat S&P) was shifted DOWN to {long_p:.2f} from a base rate of {base:.2f}"
            )
        if long_excess < -0.02 and long_p > base + 1e-9:
            issues.append(
                f"the expected return trails the index by {long_excess:+.1%}/yr, but "
                f"P(beat S&P) was shifted UP to {long_p:.2f} from a base rate of {base:.2f}"
            )

    # --- the $10,000 answer ----------------------------------------------
    answer = (verdict_card or {}).get("ten_thousand_dollar_answer") or {}
    choice = answer.get("choice")
    if choice and long_excess is not None:
        if choice == "this_stock" and long_excess < 0:
            issues.append(
                f"the $10,000 answer picks this stock, but its expected return trails the "
                f"index by {long_excess:+.1%}/yr"
            )
        if choice == "sp500" and long_excess > 0.02:
            issues.append(
                f"the $10,000 answer picks the index, but the stock's expected return beats "
                f"it by {long_excess:+.1%}/yr"
            )

    return {"ok": not issues, "issues": issues}
