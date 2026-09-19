# P2 score rubric

Owner: P2 (Calc, Audit & Eval). Referenced by `calc.api.derive_scores` and
`plan.txt` 15.14 P2 step 4 ("fixed rubric mapping excess return ... to 1..10.
Document the rubric ... Never inflate").

## Inputs

`derive_scores` (in `calc/scenarios.py`) works from `scenario_result.json`:

- `excess_vs_sp500["5y"]` - the probability-weighted annualized return from
  the bear/base/bull scenarios, minus the assumed S&P 500 return
  (`config.SP500_EXPECTED_ANNUAL_RETURN`, currently 0.07/yr).
- `scenarios.bear.annualized_return` - the worst-case scenario's return, used
  as an uncertainty check.

The LLM never sets the score directly (plan.txt error C): it only proposes
scenario inputs (`scenarios.json`), and every number downstream of that is
computed here.

## Step 1: base score from excess return

`excess_vs_sp500["5y"]` is looked up in a fixed table of bands
(`calc/config.py: SCORE_BANDS`):

| excess return (annualized) | score |
|-----------------------------|-------|
| < -0.10                     | 1     |
| -0.10 to -0.07               | 2     |
| -0.07 to -0.04               | 3     |
| -0.04 to -0.01               | 4     |
| -0.01 to 0.01                | 5     |
| 0.01 to 0.04                 | 6     |
| 0.04 to 0.07                 | 7     |
| 0.07 to 0.10                 | 8     |
| 0.10 to 0.15                 | 9     |
| > 0.15                      | 10    |

If `excess_vs_sp500` is `unavailable` (missing scenario data), the score
defaults to **5** (neutral/unknown) rather than inventing a confident number
in either direction.

## Step 2: uncertainty penalty

If the **bear** scenario's annualized return is at or below
`config.SEVERE_DOWNSIDE_RETURN` (-0.25/yr), subtract
`config.SEVERE_DOWNSIDE_PENALTY` (1 point), floored at 1. This keeps a stock
with a plausible severe-downside path from ever reading as a "10" purely
because its probability-weighted expected case looks good - the rubric must
show its work when the bull case is doing the lifting (plan.txt error D: show
sensitivity, don't collapse it to a single confident number).

## short_term / medium_term / long_term

All three currently use the same `excess_vs_sp500` input value (the 5-year
scenario returns are annualized and applied uniformly across horizons,
matching how `scenario_result.excess_vs_sp500` is computed in
`calc/scenarios.py`). The rubric itself is written per-horizon
(`excess_vs_sp500["1y"|"3y"|"5y"]`) so that if `evaluate_scenarios` later
gains genuinely horizon-specific expected returns, `derive_scores` does not
need to change.

## Why a fixed table instead of a formula

A human can audit a table in one glance and it can't silently drift when
someone tweaks an unrelated constant. If the bands ever change, update this
file and `calc/config.py: SCORE_BANDS` in the same change, and update
`fixtures/mock/scenario_result.json` / `verdict.json` if the ACME expected
scores move (that fixture is coordinator-owned - file a
`docs/requests/` note if it needs to change).
