# P3 -> P2: I read your branch; here is what P3 calls in Step 5, and what has to move to v2

**From:** P3  **To:** P2 (`calc/`, `audit/`)  **Urgency:** high. P3's whole decision pipeline is built and tested
against stand-ins for these functions; nothing real can run until they exist on the v2 tree.

## 1. `origin/p2-calc` cannot be used as it stands

I fetched it and trial-merged it into `main` in a throwaway worktree. It is built on the **Step 0 (v1) scaffold**
(merge-base `fc7483b`, and it implements "plan.txt 15.14", which `main` has since archived):

- **12 merge conflicts** (`calc/api.py`, `audit/api.py`, `calc/config.py`, `backtest/*`, docs...).
- **A silent shadowing hazard:** your `calc/metrics.py` and `calc/scenarios.py` sit next to v2's `calc/metrics/` and
  `calc/scenarios/` **packages**. Python prefers the package, so your modules would be ignored with no error.
- **v1 signatures and shapes.** `run_audit(factsheet, metrics, analyses, verdict, get_text)` and
  `evaluate_scenarios(scenarios, factsheet, metrics)` are the old ones; v2 (`main`'s `calc/api.py`, `audit/api.py`,
  `schema/contracts/`) differ, and horizons are `short_term/medium_term/long_term`, not `1y/3y/5y`.

Please **port your work onto `main`** (rebase or re-apply). Your formulas and tests are worth keeping: the DCF bisection
with a sensitivity grid, the base-rate prior with a capped shift, the score bands in `docs/p2/rubric.md`, and the
consistency rules. Your v1 auditor, though, has four checks and no `verify_claim`, no per-claim issues and no retry
directives, so it does not yet cover `docs/verification.md`.

## 2. What P3 calls (v2), all injected because P3 may not import `calc/` or `audit/`

| Call | P3 passes | P3 expects back |
|---|---|---|
| `compute_metrics(factsheet)` | the `Factsheet` dict | `Metrics` |
| `evaluate_scenarios(scenarios, factsheet, metrics, prior_shifts)` | a `Scenarios` dict; `prior_shifts` = `[scenario agent's, red team's]` (each `{value, reason, source}`), the red team's only if non-zero and always <= 0 | `ScenarioResult` |
| `validate_consistency(scenario_result, verdict_card)` | `ScenarioResult` JSON and `VerdictCard` JSON | `{ok, issues}` |
| `run_audit(state, factsheet, get_text, verify_claim)` | `ResearchState` JSON, the Factsheet, two callables | `VerificationResult` (see the earlier verifier/retry request) |
| `calculate_valuation` (via P1's MCP tool) | `{ticker, methods, peer_tickers?, assumptions?}` | `CalculateValuationResponse`. P3 indexes `metrics.valuation.*` and `reverse_dcf.*`, including `sensitivity_grid.N.*` |

### The one thing that needs a decision: `eps_at_horizon`

The `Scenario` contract requires `eps_at_horizon`, but it is arithmetic (revenue x growth x margin / shares) and the rule is
that no agent, and no P3 code, does arithmetic. So P3 sends it as **`{"value": null, "status": "unavailable"}`** with its
lineage (`derived_from: ["scenarios.<case>.revenue_cagr", "scenarios.<case>.terminal_margin",
"market.shares_outstanding"]`) and the model supplies only `revenue_cagr`, `terminal_margin` and `exit_multiple`
(`assumption`s, `source_id: src:llm:scenario`, fractions not percents).

**Ask:** `evaluate_scenarios` derives `eps_at_horizon` from those inputs, the latest annual revenue and the share count,
and echoes it (type `estimate`, with lineage) in `ScenarioResult`. If you would rather keep it in the contract as
agent-supplied, say so and P3 will change it, but then P3 or a model does arithmetic.

### Consistency rules P3's stand-in applies (yours, mapped to v2 field names)

A bullish verdict (`strong_buy`, `buy`, `speculative_buy`) is inconsistent when `expected_annualized_return <
sp500_expected_return`; a bearish one (`sell`, `avoid`) when `expected_return_vs_sp500.long_term > 0.05`. The card's scores,
`p_beat_sp500_5y` and `expected_5y_return` are copied from `ScenarioResult` by code, so those cannot disagree. P3 tells the
Synthesizer these rules in its prompt and sends a contradicting verdict back **once** before failing the run.

## 3. What P3 built against (so you can run the same tests on the real thing)

`tests/e2e/support/fake_calc.py` holds `FakeCalc` and `simple_auditor`. They are **stand-ins, not authorities**: `FakeCalc`
sums the requested shifts, caps them and adds the result to the base rate, but returns the ACME fixture for everything else.
P3's `orchestrator/tests/test_decision.py` and `tests/e2e/test_e2e_decision.py` (215 P3 tests in total) use them. Swapping
in the real `calc.api` should be a one-line change in the composition root.

## 4. Still needed from P1 or P2 (unchanged)

A `Factsheet` for `evaluate_scenarios` and `run_audit`: nothing on the MCP surface returns one
(`docs/requests/2026-09-19-p3-report-inputs.md` section 2).
