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
DSO_INCREASE_FLAG = 0.05
"""Days-sales-outstanding rise (fraction, year over year) that raises a flag.

Lowered from 0.10 when the flag was implemented (Step 1): receivables growing 5%
faster than revenue is the point at which the trend is visible at all, and the
severity steps below are what separate "worth a line in the report" from
"worth the reader's attention". Reasoning recorded in docs/p2/rubric.md.
"""

SBC_REVENUE_FLAG = 0.05
"""Stock compensation above this share of revenue raises a flag."""

FCF_CONVERSION_FLAG = 0.70
"""FCF / net income below this raises a flag: reported profit is not turning
into cash."""

INVENTORY_DAYS_FLAG = 0.05
"""Days-inventory rise (fraction, year over year) that raises a flag."""

BUYBACK_FLAG = 0.02
"""Share-count shrinkage (fraction) above which EPS growth is partly a buyback."""

FLAG_SEVERITY_STEPS: tuple[float, float, float] = (1.0, 3.0, 6.0)
"""Multiples of a flag threshold that map to low / medium / high severity.

One number per flag plus one shared ladder, so a reader can see the whole
severity scheme at a glance instead of nine separate constants.
"""

# --------------------------------------------------------------------------
# Per-share comparability
# --------------------------------------------------------------------------
SHARE_BASIS_BREAK_RATIO = 1.5
"""Year-over-year diluted share-count ratio that means the share basis changed.

A 10-K restates only the two comparative years it shows, so an older year can sit
in the series on a pre-split basis while being correct as filed (NVDA FY2022,
9.9x). Above this ratio calc/ refuses per-share comparisons across the boundary
unless P1 published a `_split_adjusted` fact (P1 -> P2, 2026-09-19).
"""

# --------------------------------------------------------------------------
# Reverse DCF solver
# --------------------------------------------------------------------------
DCF_SOLVE_LOW = -0.5
DCF_SOLVE_HIGH = 1.0
DCF_SOLVE_ITERATIONS = 200
"""Bisection bracket and iteration count. 200 halvings of a 1.5-wide bracket is
far past double precision, so the answer is deterministic to the last digit."""

# --------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------
PEER_MIN_SAMPLE = 2
"""Fewest peer values that may form a median. One peer is not a comparison."""

# --------------------------------------------------------------------------
# Scoring, continued
# --------------------------------------------------------------------------
SCORE_NEUTRAL = 5
"""The score for "we do not know". Never 1 and never 10: an unavailable expected
return is not evidence either way."""

SCORE_FLOOR = 1
SCORE_CEILING = 10

SCORE_HORIZON_UNCERTAINTY: dict[str, float] = {
    "short_term": 1.0,
    "medium_term": 1.25,
    "long_term": 1.5,
}
"""How much to discount the same excess return as the horizon lengthens.

The scenario model produces ONE annualized return, so without this every horizon
would score identically. Dividing the excess by these factors pulls the long
horizon toward neutral, which is honest: our ability to tell a 3-5 year winner
from a loser is worse than our ability to tell a 12-month one, and the score
should say so rather than repeating the same confident number three times.
"""

SEVERE_DOWNSIDE_RETURN = -0.25
"""Bear-case annualized return at or below which the score loses a point."""

SEVERE_DOWNSIDE_PENALTY = 1
"""Points subtracted when the bear case is severe, floored at SCORE_FLOOR.

Stops a stock with a plausible -25%/yr path from reading as a high score purely
because the bull case is doing the lifting in the weighted average.
"""

# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------
CONFIG_SOURCE = "calc_assumptions"
"""Name used in src:config:<name> for every constant in this module."""
