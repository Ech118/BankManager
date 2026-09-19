# calc/ — P2 Compute Engine

**Owner: P2.** Rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).

Every number in the product is computed here. No agent does arithmetic
([ADR 0001](../docs/adr/0001-code-computes-llm-interprets.md)).

## Public interface

`calc/api.py` only.

| Function | Purpose |
|---|---|
| `compute_metrics(factsheet)` | margins, growth, FCF, balance sheet, valuation |
| `reverse_dcf(factsheet, metrics, assumptions=None)` | implied growth + sensitivity grid |
| `calculate_valuation(request)` | the MCP-exposed entry point |
| `evaluate_scenarios(scenarios, factsheet, metrics, prior_shifts=None)` | bounded weights, returns, P(beat S&P) |
| `derive_scores(scenario_result)` | 1–10 via the fixed rubric |
| `validate_consistency(scenario_result, verdict_card)` | the four outputs must agree |

**No function takes both a factsheet and an `as_of`.** The factsheet's `as_of`
is authoritative; a second date could silently disagree. `test_signatures.py`
enforces this.

## Purity

No network, no database, no filesystem beyond the mock fixtures, no LLM — ever.
Given the same inputs, the same outputs. That is what makes `audit/`'s recompute
check meaningful: it re-derives the number and compares.

## Layout

```
config.py      every tunable constant, each tagged ASSUMPTION
lineage.py     derived values that carry formula + inputs
metrics/       fcf, margins, growth, sbc_dilution, working_capital
valuation/     multiples, peers, historical, dcf, reverse_dcf
scenarios/     evaluate (weight bounding), prior (cap), rubric, consistency
```

## The two bounds on the LLM

Both live here because the agent cannot reach them.

1. **Scenario weights** — the agent proposes bear/base/bull weights with
   reasons; `scenarios/evaluate.py` clamps each into
   `default ± SCENARIO_WEIGHT_BAND`, redistributes the residual across the
   *unclamped* weights, and records every clamp in `ScenarioWeights`. Clamped,
   never silently dropped.
2. **The prior shift** — `P(beat S&P)` starts at the historical base rate
   (~40–45% at five years). The Scenario Agent and the Red Team may each request
   a tilt with a written reason; their sum is capped at `PRIOR_SHIFT_CAP`.
   Requested and applied are both recorded.

## Dependencies

`calc/requirements.txt`. P2 depends on no other partition.
