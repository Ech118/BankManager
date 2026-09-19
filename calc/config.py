"""Assumption constants for calc/. Every number here is tagged type "assumption"
or "estimate" wherever it reaches an output artifact (never "fact") - see
plan.txt error D. Changing these is a P2-internal tuning decision, not a
schema change, so it does not need a docs/requests/ file - but document any
change in docs/p2/rubric.md or docs/p2/STATUS.md so P3/demo narration stays in
sync.
"""

SOURCE_CONFIG = "src:config:calc_assumptions"

# --- reverse DCF (plan.txt error D) --------------------------------------
DEFAULT_DISCOUNT_RATE = 0.09
DEFAULT_TERMINAL_GROWTH = 0.03
DEFAULT_DCF_HORIZON_YEARS = 10

# Sensitivity grid axes (plan.txt: "ALWAYS return a sensitivity grid").
DCF_SENSITIVITY_DISCOUNT_RATES = (0.08, 0.09, 0.10)
DCF_SENSITIVITY_TERMINAL_GROWTHS = (0.02, 0.03, 0.04)

# Bisection bounds/iterations for the implied-growth solver.
DCF_SOLVE_LOW = -0.5
DCF_SOLVE_HIGH = 1.0
DCF_SOLVE_ITERATIONS = 200

# --- scenario evaluation (plan.txt error C) -------------------------------
SP500_EXPECTED_ANNUAL_RETURN = 0.07  # type "assumption"

# Historical base rate that an individual stock beats the S&P 500 over N
# years (plan.txt 13.C: "historically only roughly 40-45% ... over 5 years").
# These are our own documented priors, not fetched from anywhere - source_id
# is SOURCE_CONFIG.
BASE_RATE_P_BEAT_SP500 = {"1y": 0.47, "3y": 0.44, "5y": 0.42}

# The LLM's prior_shift request is capped to +/- this many probability points
# (plan.txt: "e.g. +/-0.15"). This is the hard defence against error C.
PRIOR_SHIFT_CAP = 0.15

# --- quality flags (plan.txt: "DSO/inventory trend flags") ---------------
DSO_FLAG_LOW_PCT = 0.05      # DSO grew 5-15% YoY -> low severity
DSO_FLAG_MEDIUM_PCT = 0.15   # 15-30% -> medium
DSO_FLAG_HIGH_PCT = 0.30     # >30% -> high

INVENTORY_DAYS_FLAG_LOW_PCT = 0.05
INVENTORY_DAYS_FLAG_MEDIUM_PCT = 0.15
INVENTORY_DAYS_FLAG_HIGH_PCT = 0.30

BUYBACK_FLAG_LOW_PCT = 0.02   # dilution_yoy more negative than -2% -> low
BUYBACK_FLAG_MEDIUM_PCT = 0.05
BUYBACK_FLAG_HIGH_PCT = 0.10

# --- score rubric (docs/p2/rubric.md is the authoritative writeup) -------
# Ordered (upper_bound_exclusive, score) bands over annualized excess return
# vs the S&P 500 assumption. The last band has no upper bound.
SCORE_BANDS = [
    (-0.10, 1),
    (-0.07, 2),
    (-0.04, 3),
    (-0.01, 4),
    (0.01, 5),
    (0.04, 6),
    (0.07, 7),
    (0.10, 8),
    (0.15, 9),
]
SCORE_BAND_TOP = 10  # excess > last band's threshold

# If the bear-case annualized return is at or below this, we do not let the
# rubric hand out a top-tier score even when the probability-weighted excess
# return looks good (uncertainty penalty, plan.txt 13.D "show sensitivity").
SEVERE_DOWNSIDE_RETURN = -0.25
SEVERE_DOWNSIDE_PENALTY = 1
