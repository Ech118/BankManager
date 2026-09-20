# P2 score rubric

Owner: P2 (Calc, audit & eval). Implemented by `calc/scenarios/rubric.py`, with
every constant in [`calc/config.py`](../../calc/config.py).

This file has to exist before `derive_scores` can go real
([STATUS.md](STATUS.md)), because a score a reader cannot audit is worse than no
score: it reads as a measurement and is actually a choice.

---

## Inputs

`derive_scores(scenario_result)` reads two things, both computed by
`calc.evaluate_scenarios`:

- **`excess_vs_sp500[horizon]`** - the probability-weighted annualized return
  from the bear/base/bull cases, minus the assumed S&P 500 return
  (`sp500_expected_return`, 0.07/yr from `config.SP500_EXPECTED_RETURN` unless a
  factsheet publishes its own).
- **`scenarios.bear.annualized_return`** - the worst case, used as an uncertainty
  check.

The LLM never sets a score. It proposes scenario inputs and weights; every number
downstream of that is computed here (ADR 0001, error C).

---

## Step 1: discount the excess for the horizon

The scenario model produces **one** annualized return, so without this step all
three horizons would score identically. The excess is divided by
`config.SCORE_HORIZON_UNCERTAINTY` before lookup:

| horizon | divisor | why |
|---|---|---|
| `short_term` (0-12m) | 1.00 | the claim we can best support |
| `medium_term` (1-3y) | 1.25 | |
| `long_term` (3-5y) | 1.50 | a five-year call is a weaker claim than a one-year one |

Dividing pulls long horizons **toward neutral in both directions**: it is not a
penalty on bad stocks or a bonus for good ones, it is a statement that our
ability to tell them apart falls off with time. A 3/10 at twelve months becoming
a 4/10 at five years says "still bad, less certainly".

---

## Step 2: the band table

The discounted excess is looked up in `config.SCORE_THRESHOLDS`, an
upper-bound table:

| discounted excess (annualized) | score |
|---|---|
| <= -0.06 | 3 |
| -0.06 to -0.02 | 4 |
| -0.02 to 0.02 | 5 |
| 0.02 to 0.06 | 6 |
| > 0.06 | 7 |

**The table tops out at 7 and bottoms at 3, on purpose.** A 10 would claim we can
identify a stock that beats the index by a wide margin over five years, and a 1
would claim the same certainty about the downside. Nothing in this pipeline
supports either. The 1-10 range exists in the contract; scores of 1, 2, 8, 9 and
10 are reachable only through step 3 or a future change to this table, and a
change needs a line here explaining why.

An **unavailable** excess scores `SCORE_NEUTRAL` (5), never 1 and never 10: not
knowing is not evidence in either direction.

---

## Step 3: the severe-downside penalty

If the **bear** case's annualized return is at or below
`config.SEVERE_DOWNSIDE_RETURN` (-0.25/yr), subtract
`config.SEVERE_DOWNSIDE_PENALTY` (1 point), floored at 1.

This stops a stock with a plausible -25%/yr path from reading as a high score
purely because the bull case is doing the lifting in a weighted average. The
weighted average is the right number for an expected return and the wrong number
for "how badly can this go".

---

## Worked example: ACME

From `fixtures/mock/scenario_result.json`:

- expected annualized return **-1.945%**, index assumption **7%**, so the excess
  is **-8.945%**/yr at every horizon;
- bear case **-14.0%**/yr, above -25%, so no penalty.

| horizon | discounted excess | band | score |
|---|---|---|---|
| short_term | -8.945% / 1.00 = **-8.95%** | <= -0.06 | **3** |
| medium_term | -8.945% / 1.25 = **-7.16%** | <= -0.06 | **3** |
| long_term | -8.945% / 1.50 = **-5.96%** | -0.06 to -0.02 | **4** |

3 / 3 / 4, which is what the pinned fixture and `verdict.json` carry.

Note how close long_term sits to its band edge (-5.96% against -6.00%): a small
change to `SCORE_HORIZON_UNCERTAINTY` or `SCORE_THRESHOLDS` moves that score.
That is a property of any band table, and it is why the table is published rather
than buried - a reader can see the score was a near thing.

---

## Why a fixed table instead of a formula

A human can audit a table at a glance, and it cannot drift when someone tweaks an
unrelated constant. Any change to the bands or the divisors updates this file in
the same commit, and if the ACME scores move, `fixtures/mock/scenario_result.json`
and `verdict.json` move with them - those are coordinator-owned, so that needs a
`docs/requests/` note.

---

## Changes to the flag and score constants

| date | constant | from | to | why |
|---|---|---|---|---|
| 2026-09-20 | `DSO_INCREASE_FLAG` | 0.10 | 0.05 | receivables growing 5% faster than revenue is where the trend is visible at all; the severity ladder separates "worth a line" from "worth attention". At 0.10 the ACME `dso_rising` flag in the pinned fixture never fired. |
| 2026-09-20 | `FLAG_SEVERITY_STEPS` | - | (1, 3, 6) | one threshold per flag plus one shared ladder, instead of nine separate constants, so the whole severity scheme is visible at once. |
| 2026-09-20 | `SCORE_HORIZON_UNCERTAINTY` | - | 1.0 / 1.25 / 1.5 | the scenario model yields one annualized return, so without a horizon term all three scores are identical. Reproduces the pinned 3/3/4. |
| 2026-09-20 | `DCF_MAX_ASSUMED_GROWTH` | - | 0.20 | NVDA's trailing FCF CAGR is 68%/yr; compounding it for ten years produces a number nobody should publish. Clamped and recorded, like a scenario weight. |
