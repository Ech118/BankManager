# P2 — Calc, audit & eval

**Owns:** `calc/`, `audit/`, `backtest/`, `predictions/`, `docs/p2/`
**Branch:** `p2-calc`
**Produces:** metrics, scenario results, audit results

## Scope

Every number in the product, and the gate that checks them:

- `calc/` — margins, growth, FCF, balance sheet, working capital, valuation
  multiples, DCF and reverse DCF
- `calc/scenarios/` — scenario weight bounding, the prior cap, the scoring
  rubric, the consistency check
- `audit/` — seven deterministic checks plus one LLM check, and retry routing
- `backtest/` — anonymizer, harness, grading, calibration
- `predictions/` — the append-only forward prediction log

## Public interfaces

`calc/api.py` and `audit/api.py`. See [calc/README.md](../../calc/README.md)
and [audit/README.md](../../audit/README.md).

## Dependencies

`schema.contracts` only. P2 depends on no other partition — `audit/` gets its
filing text and its LLM through injected callables precisely so that stays true.

`mcp_server/tools/calculate_valuation.py` (P1) imports `calc.api`. That is P1
reaching into P2, not the reverse
([ADR 0007](../adr/0007-partition-boundaries.md)).

## What P2 does not do

- Fetch data — use what you are given
- Call an LLM for anything numeric
- Edit `agents/`, `prompts/` or `web/`

## The two bounds on the LLM

Both live in P2 because agents cannot reach them.

1. **Scenario weights.** The agent proposes; `calc/` clamps into a band around
   the defaults, redistributes the residual across the *unclamped* weights, and
   records every clamp. Clamped, never silently dropped.
2. **The prior shift.** `P(beat S&P)` starts at the historical base rate. The
   Scenario Agent's and the Red Team's requests are **summed**, then capped.
   Requested and applied are both recorded.

If these are wrong, every verdict is wrong in a way that looks precise.

## Done when

- Unit tests green, including one hand-checked real filing
- The cap test proves an agent cannot exceed the prior shift
- The clamp test proves an out-of-band weight is bounded **and recorded**
- `audit/` catches an injected fake number and a fabricated quote
- The backtest runs end to end on anonymized ACME-style fixtures
