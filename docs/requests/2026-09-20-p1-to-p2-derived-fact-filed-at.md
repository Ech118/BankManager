# P1 -> P2: derived facts must carry a real `filed_at`

**From:** P1  **To:** P2 (`calc/`)  **Urgency:** low, but it silently breaks
backtests if left.

## The rule

A derived fact's `filed_at` is the **latest** `filed_at` among the facts it was
derived from, set when the fact is created. Never null.

```python
filed_at = max(f.filed_at for f in derivation_inputs)
```

## Why P2 needs it

`calc/` derives facts — FCF, margins, per-share figures — from facts P1 filed
with real dates. If those outputs carry `filed_at = null`, the point-in-time
filter cannot see them, and a backtest dated before the inputs existed will
happily include a number computed from them. That is the exact failure
[ADR 0003](../adr/0003-point-in-time-correctness.md) exists to prevent, and it
does not announce itself: the backtest runs, and is worthless.

## Why the maximum

The derived value did not exist until its last input was filed. FY2025 FCF from
an operating cash flow filed 2025-10-30 and a capex filed 2026-02-01 was not
knowable on 2025-12-01. The minimum, or the fact's period end, would both leak
it into a run that predates it.

The rule composes: a fact derived from derived facts still ends up with the date
its last *raw* input was filed, as long as every layer follows it.

## Where P1 applies it

`data/normalize/` — total debt (from its component facts) and the
split-adjusted EPS and share counts (from the as-filed fact and the split-ratio
fact). Tested in `data/tests/test_normalize.py`, including the case where the
ratio is filed after the value it adjusts.

## No contract change needed

`FinancialFact.filed_at` already exists and is already optional. This is a rule
about how to fill it, not a new field. Raised with P3 as well, in
`2026-09-19-p3-report-inputs-response.md` (their item 3).
