"""validate_consistency: score, P(beat S&P), expected return and verdict must
agree (plan.txt 15.14 P2 step 5, e.g. "verdict 'strong_buy' with expected
return below the S&P is an error").
"""
from __future__ import annotations

from calc.value import vo_value

BULLISH_VERDICTS = {"strong_buy", "buy", "speculative_buy"}
BEARISH_VERDICTS = {"sell", "avoid"}
BEARISH_EXCESS_CONTRADICTION = 0.05  # a bearish verdict despite excess return this far above zero is a warn


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Return {"ok": bool, "issues": [str]}."""
    issues: list[str] = []

    if verdict_card.get("scores") != scenario_result.get("scores"):
        issues.append("verdict card scores do not match scenario_result.scores")

    card_p_beat = verdict_card.get("p_beat_sp500_5y")
    sr_p_beat = scenario_result.get("p_beat_sp500", {}).get("5y")
    if card_p_beat != sr_p_beat:
        issues.append("verdict card p_beat_sp500_5y does not match scenario_result.p_beat_sp500['5y']")

    card_expected = vo_value(verdict_card.get("expected_5y_return"))
    sr_expected = vo_value(scenario_result.get("expected_annualized_return"))
    if card_expected is not None and sr_expected is not None and abs(card_expected - sr_expected) > 1e-9:
        issues.append("verdict card expected_5y_return does not match scenario_result.expected_annualized_return")

    verdict = verdict_card.get("verdict")
    sp500_expected = vo_value(scenario_result.get("sp500_expected_return"))
    excess_5y = vo_value(scenario_result.get("excess_vs_sp500", {}).get("5y"))

    if verdict in BULLISH_VERDICTS and sr_expected is not None and sp500_expected is not None \
            and sr_expected < sp500_expected:
        issues.append(f"verdict '{verdict}' but expected return is below the S&P 500 assumption")

    if verdict in BEARISH_VERDICTS and excess_5y is not None and excess_5y > BEARISH_EXCESS_CONTRADICTION:
        issues.append(f"verdict '{verdict}' despite excess return {excess_5y:.3f} well above the S&P 500")

    upstream = scenario_result.get("consistency", {})
    if upstream and not upstream.get("ok", True):
        issues.extend(upstream.get("issues", []))

    return {"ok": not issues, "issues": issues}
