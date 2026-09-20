"""The base-rate prior for P(beat S&P), and the cap on moving it.

Specified by docs/pipeline.md and docs/adr/0001 (plan review error C).

WHY A PRIOR AT ALL. Asked directly, a language model will produce a
confident-sounding probability that a stock beats the index, and that number
will move between runs on the same inputs. Anchoring on the historical base rate
(~40-45% over five years, because index returns concentrate in a few big
winners) and letting agents move it only within a capped range turns an
invention into an adjustment that has to be argued for.

WHO MAY REQUEST A SHIFT. The Scenario Agent and the Red Team, each with a
written reason. Their requests SUM, and the sum is capped. The Red Team's shift
is always downward in practice, which is the point: something in the pipeline
should be able to argue the verdict down.

Requested and applied are recorded separately, so an overruled agent stays
visible in the output.
"""

from __future__ import annotations

from calc import config

UNJUSTIFIED = "a prior shift without a written reason is not applied"
"""An unreasoned shift is dropped, not capped. The reason is the whole argument."""


def base_rate() -> dict[str, float]:
    """Historical P(beat S&P) per horizon, from config.BASE_RATE_P_BEAT_SP500."""
    return dict(config.BASE_RATE_P_BEAT_SP500)


def apply_shifts(shifts: list[dict] | None) -> dict:
    """Sum the requested shifts, cap the total, record requested vs applied.

    The cap is symmetric and absolute: |applied| <= cap, and |applied| may never
    exceed |requested| (code may shrink a request, never enlarge it).

    A shift with no reason is DROPPED before the sum. It is not counted and then
    overruled - it never joins the argument, and `dropped_shifts` says so.
    """
    cap = config.PRIOR_SHIFT_CAP
    kept: list[dict] = []
    dropped: list[str] = []
    for shift in shifts or []:
        if not isinstance(shift, dict) or shift.get("value") is None:
            continue
        reason = (shift.get("reason") or "").strip()
        source = shift.get("source") or "scenario"
        if not reason:
            dropped.append(f"{source}: {UNJUSTIFIED}")
            continue
        kept.append({"value": float(shift["value"]), "reason": reason, "source": source})

    requested = sum(shift["value"] for shift in kept)
    applied = max(-cap, min(cap, requested))
    prior = {
        "base_rate": base_rate(),
        "requested_shift": round(requested, 10),
        "applied_shift": round(applied, 10),
        "cap": cap,
        "shift_reasons": [f"{shift['source']}: {_lower_first(shift['reason'])}" for shift in kept],
    }
    if dropped:
        prior["dropped_shifts"] = dropped
    if applied != requested:
        prior["cap_applied"] = True
        prior["cap_note"] = (
            f"the agents together asked for {requested:+.2f} against a hard cap of "
            f"{cap:.2f}, so {applied:+.2f} was applied"
        )
    return prior


def p_beat_sp500(prior: dict) -> dict[str, float]:
    """Base rate plus the applied shift, clipped to [0, 1], per horizon."""
    shift = prior["applied_shift"]
    return {
        horizon: round(max(0.0, min(1.0, rate + shift)), 10)
        for horizon, rate in prior["base_rate"].items()
    }


def _lower_first(text: str) -> str:
    """Match the fixture's "scenario: stock trades at..." style."""
    return text[0].lower() + text[1:] if text else text
