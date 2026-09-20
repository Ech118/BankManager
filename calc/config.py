"""Every tunable constant in the system, in one auditable place.

Specified by docs/pipeline.md and docs/adr/0001.

Two reasons this is a module and not scattered literals:

1. EVERY VALUE HERE IS AN ASSUMPTION, and the report colour-codes it as one.
   A discount rate is a choice, not a fact, and a reader deserves to see which
   is which (error D).

2. THESE ARE THE BOUNDS ON THE LLM. The scenario weight band and the prior cap
   are what stop an agent from asserting whatever probability suits its
   narrative. They belong in code the agent cannot reach (error C).

Changing a number here changes every verdict, so changes need a line in
docs/p2/rubric.md explaining the reasoning.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Discounted cash flow
# --------------------------------------------------------------------------
DISCOUNT_RATE = 0.09
"""Cost of capital used by the reverse DCF. ASSUMPTION."""

TERMINAL_GROWTH = 0.03
"""Perpetual growth after the horizon. ASSUMPTION. Must stay below DISCOUNT_RATE."""

DCF_HORIZON_YEARS = 10
"""Explicit forecast horizon before the terminal value."""

SENSITIVITY_DISCOUNT_RATES = (0.08, 0.09, 0.10)
SENSITIVITY_TERMINAL_GROWTHS = (0.02, 0.03, 0.04)
"""The grid. A reverse DCF must NEVER be reported as a single point (error D)."""

# --------------------------------------------------------------------------
# Scenario weights: the bounds on the Scenario Agent
# --------------------------------------------------------------------------
DEFAULT_SCENARIO_WEIGHTS: dict[str, float] = {"bear": 0.30, "base": 0.50, "bull": 0.20}
"""Priors on the three cases. The agent argues away from these, within the band."""

SCENARIO_WEIGHT_BAND = 0.15
"""How far a requested weight may sit from its default.

An agent that wants a 90% bull case is not forecasting, it is asserting. The
band lets it express conviction while keeping the expected value anchored.
Requests outside the band are CLAMPED and RECORDED, never silently accepted and
never silently discarded (amendment 1).
"""

# --------------------------------------------------------------------------
# P(beat S&P): the bounds on every agent
# --------------------------------------------------------------------------
BASE_RATE_P_BEAT_SP500: dict[str, float] = {
    "short_term": 0.47,
    "medium_term": 0.44,
    "long_term": 0.42,
}
"""Historical share of individual stocks beating the index, by horizon.

Roughly 40-45% over five years: index returns are driven by a small number of
big winners, so the median stock lags. Starting every company from this prior
means an optimistic verdict has to earn its optimism (error C).
"""

PRIOR_SHIFT_CAP = 0.15
"""Maximum total tilt away from the base rate, summed over all agents.

Both the Scenario Agent and the Red Team may request a shift, each with a
written reason. The sum is capped here. calc/ records requested and applied
separately, so an overruled request stays visible.
"""

SP500_EXPECTED_RETURN = 0.07
"""Assumed annual index return. ASSUMPTION, and the benchmark every verdict
is measured against."""

# --------------------------------------------------------------------------
# Scoring rubric
# --------------------------------------------------------------------------
SCORE_THRESHOLDS: tuple[tuple[float, int], ...] = (
    (-0.06, 3),
    (-0.02, 4),
    (0.02, 5),
    (0.06, 6),
    (float("inf"), 7),
)
"""Excess-return upper bound -> score. Documented in docs/p2/rubric.md.

Deliberately compressed around the middle: the difference between a 5 and a 6 is
small because our ability to tell them apart is small.
"""

# --------------------------------------------------------------------------
# Quality flag thresholds
# --------------------------------------------------------------------------
DSO_INCREASE_FLAG = 0.10
"""Days-sales-outstanding rise (fraction, year over year) that raises a flag."""

SBC_REVENUE_FLAG = 0.05
"""Stock compensation above this share of revenue raises a flag."""

FCF_CONVERSION_FLAG = 0.70
"""FCF / net income below this raises a flag: reported profit is not turning
into cash."""

INVENTORY_DAYS_INCREASE_FLAG = 0.10
"""Days-inventory-outstanding rise (fraction, year over year) that raises a flag.
Same semantics as DSO_INCREASE_FLAG: above this, severity steps up from low."""

BUYBACK_DILUTION_FLAG = 0.02
"""|dilution_yoy| above this, when it is negative and EPS grew, raises
buyback_flatters_eps: severity steps up from low as the buyback gets larger."""
