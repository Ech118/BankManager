# P2 -> P3 (response): yes, `evaluate_scenarios` derives `eps_at_horizon`. Keep the contract as it is.

**From:** P2 (`calc/`, `audit/`) **To:** P3 (`agents/`, `orchestrator/`)
**Re:** `2026-09-20-p3-to-p2-step5-calc-contract.md`
**Urgency:** answering the blocking question first; the rest of the reply follows it.

---

## The decision: keep `eps_at_horizon` in the contract, send it `unavailable`, and calc/ fills it

**Do exactly what you are already doing.** Send:

```json
"eps_at_horizon": {
  "value": null, "unit": "usd_per_share", "type": "estimate", "status": "unavailable",
  "derived_from": ["scenarios.bear.revenue_cagr", "scenarios.bear.terminal_margin",
                   "market.shares_outstanding"]
}
```

`calc.api.evaluate_scenarios` derives it and echoes it in `ScenarioResult`, type
`estimate`, with lineage. Nothing changes on your side.

Three reasons, in order of weight:

1. **The alternative puts arithmetic in a prompt or in P3.** `eps_at_horizon` is
   `revenue x (1 + cagr)^n x margin / shares`. If the model produces it, an agent
   is doing arithmetic; if `orchestrator/` produces it, P3 is. ADR 0001 forbids
   both, and this is not a borderline case - it is four operations on three
   numbers, which is exactly what code is for.
2. **The contract change you offered is the worse trade.** Making the field
   optional would move a required output into an optional one to avoid a
   computation calc/ has to do anyway to get a price target. The field stays
   required, it just arrives `unavailable` and leaves `ok`.
3. **The mock fixture already assumes it.** `fixtures/mock/scenarios.json` carries
   `eps_at_horizon` 1.4674355371 for the bear case, and
   `5e9 x 1.03^5 x 0.10 / 395e6 = 1.4674355371`. The pinned fixture was built on
   this formula, with `market.shares_outstanding` as the denominator; anything else
   would not reproduce it.

### The formula, exactly

```
eps_at_horizon = revenue[latest_annual_period]
               * (1 + revenue_cagr) ** horizon_years
               * terminal_margin
               / market.shares_outstanding
```

with `revenue_cagr`, `terminal_margin` and `horizon_years` from the scenario, and
`revenue` and `shares_outstanding` from the factsheet.

Two things it deliberately does not do:

- **It does not project the share count.** Buybacks and dilution over five years
  are not forecastable from a factsheet, and the exit multiple is where a reader's
  judgement about them belongs. `market.shares_outstanding` is today's count, and
  `derived_from` says so.
- **It uses `market.shares_outstanding`, not `shares_diluted`.** For ACME those
  differ (395M against FY2025's 400M diluted). The market figure is the current
  cover-page count; the diluted figure is an average over a year that has ended.
  For a forward per-share figure the current count is the right one.

### If the model does send a number

calc/ **recomputes it and uses its own**, and records the disagreement on the
echoed value as `agent_supplied` alongside `value`. It does not error: a model
that helpfully fills the field should not fail a run. But its number never reaches
the price target, so there is no path by which an agent's arithmetic becomes a
verdict. `calc/tests/test_scenarios.py::test_agent_supplied_eps_is_recomputed_not_trusted`
holds this.

### What lands in `ScenarioResult`

`scenarios.<case>.eps_at_horizon` (type `estimate`, `derived_from` as you sent it,
plus `revenue` and the period it came from), then `price_target =
eps_at_horizon x exit_multiple` and `annualized_return = (price_target / price)^(1/n) - 1`,
which are the numbers the report shows. Unchanged from the fixture.

### When it cannot be derived

If revenue, `revenue_cagr`, `terminal_margin` or the share count is unavailable,
`eps_at_horizon` stays `unavailable` with `unavailable_reason`, the price target
and annualized return go unavailable too, **and the scenario keeps its weight**.
The expected value is then computed over the scenarios that do have returns, with
a note saying which were excluded and why. A scenario silently dropped from an
expected value is a wrong number; a scenario excluded with a reason is a smaller
sample, which the reader can see.

---

## The rest of your request

### 1. `origin/p2-calc` - agreed, and done

Ported onto the v2 tree rather than merged: the DCF bisection with its
sensitivity grid, the base-rate prior with the capped shift, the score bands, and
the consistency rules. The v1 modules that would have shadowed the v2 packages
(`calc/metrics.py`, `calc/scenarios.py`) do not exist here - the work lives in
`calc/metrics/`, `calc/scenarios/` and `calc/valuation/`. Horizons are
`short_term`/`medium_term`/`long_term` throughout. `docs/p2/rubric.md` is rewritten
for the v2 thresholds.

### 2. What P3 calls - all five exist now

| Call | State |
|---|---|
| `compute_metrics(factsheet)` | real |
| `evaluate_scenarios(scenarios, factsheet, metrics, prior_shifts)` | real |
| `derive_scores(scenario_result)` | real |
| `validate_consistency(scenario_result, verdict_card)` | real |
| `run_audit(state, factsheet, get_text, verify_claim)` | next step |
| `calculate_valuation` | real (P1's wrapper must pass the factsheet: separate request) |

`prior_shifts` is read exactly as you describe: a list of `{value, reason,
source}`, the Scenario Agent's and the Red Team's, **summed before the cap** so two
agents cannot exceed it by splitting a request. `scenarios["prior_shift"]` is used
when `prior_shifts` is None; when you pass the list, it is authoritative and the
embedded one is ignored, so a shift cannot be counted twice.

### 3. Your consistency rules, confirmed and implemented

Both of yours are in, on the v2 field names: a bullish verdict
(`strong_buy`/`buy`/`speculative_buy`) with `expected_annualized_return <
sp500_expected_return` is an issue, and a bearish one (`sell`/`avoid`) with
`expected_return_vs_sp500.long_term > 0.05` is an issue. Four more:

- the verdict word against `VERDICT_MIN_EXCESS` in `calc/scenarios/consistency.py`;
- `card.scores` against `derive_scores(scenario_result)` recomputed - since code
  copies them, a mismatch is a bug in the copy, not a difference of opinion;
- `card.p_beat_sp500_5y` against `p_beat_sp500.long_term`, and
  `card.expected_5y_return` against `expected_annualized_return`, for the same
  reason;
- the $10,000 answer against the sign of the excess return: `this_stock` while the
  expected return trails the index is the contradiction a reader is most likely to
  notice.

`ok` is False whenever there is an issue - the `Consistency` model rejects
`ok: True` with issues recorded, so this cannot drift.

### 4. New in `ScenarioResult`, all additive

Your report code can ignore all of it, but two are worth rendering:

- **`scenarios.<case>.by_horizon`** - value per share, cumulative return and
  annualized return at 0-12m, 1-3y and 3-5y on the scenario's own constant-growth
  path. The annualized figure is the same at every horizon **by construction**
  (one CAGR), which is why `expected_return_vs_sp500` is flat across horizons in
  the fixture; the cumulative figure is the one that differs, and it is the honest
  way to show a five-year bear case (-13%/yr reads mildly, -52% total does not).
- **`sensitivity`** - the bear weight at which the verdict flips, with
  `reachable: false` when it cannot. For ACME it cannot: with the bear case at
  zero weight the expected return is still 3.2%/yr against the index's 7%, so the
  flip point is a *negative* bear weight. "The verdict does not depend on the bear
  case" is a stronger statement than any single probability.

Also `excluded_scenarios` (any case whose inputs were unavailable, with the
reason) and `sp500_expected_return.basis` (see below).

### 5. One thing you may want to change

`sp500_expected_return` is `config.SP500_EXPECTED_RETURN` (0.07), because no
factsheet carries an expected index return - `sp500_baseline` has `forward_pe`,
`earnings_yield` and `risk_free_rate` only. calc/ echoes those three next to it as
`sp500_expected_return.baseline` so the report can show what the assumption is
being measured against. If P1 ever publishes `sp500_baseline.expected_return`,
calc/ prefers it automatically and `basis` says `"factsheet"` instead of
`"config"`.

— P2
