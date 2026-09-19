# ADR 0003 — Point-in-time correctness

**Status:** accepted (Step 0)

## Context

Any claim that this system works has to rest on evaluation, and the obvious
evaluation is a backtest: run the pipeline on a 2022 filing and see what
happened next.

Two things quietly destroy that.

**Data leakage.** The SEC's `companyfacts` endpoint returns the *latest* value
for every concept. A company that restated FY2021 in 2023 will serve the
corrected figure with no indication it changed. A "2022" run then reasons about
numbers that did not exist in 2022.

**Model memory.** The model's training data already contains what happened to
most public companies. This one cannot be fully solved, only reduced and
disclosed.

## Decision

**Every data query takes an `as_of` date and returns only data filed or observed
before it.**

- Every method on `FactRepository`, `FilingRepository` and `MarketRepository`
  takes `as_of`.
- Every MCP data tool request inherits `DataToolRequest`, which makes `as_of`
  **required**. A data tool cannot be defined without one.
- Historical runs use per-filing XBRL (`companyconcept`), never `companyfacts`.
- Restatements set `superseded_by`; the as-filed row survives, so
  "what did we know on date D" has an answer.
- `audit/` raises `future_fact` if any cited fact post-dates the run.

Against model memory, three partial defences, and a requirement to say which was
used: point-in-time data, anonymization (`backtest/anonymize.py`), and the
forward prediction log (`predictions/`).

**No function that receives a factsheet also takes an `as_of`.** The factsheet's
own `as_of` is authoritative; a second parameter could silently disagree, and
`tests/contracts/test_signatures.py` enforces this.

## Consequences

**Good**

- The backtest is meaningful, within the limits of the memory problem.
- The restatement model is genuinely useful outside the backtest: "what did
  management report at the time" is a real research question.
- A single `as_of` per run means no component can disagree with another about
  what date it is.

**Costs**

- Materially more work in P1 — per-filing XBRL instead of one convenient
  endpoint.
- Every repository signature carries `as_of`, including where it feels
  redundant.
- Model memory is never fully solved. The forward log is the only clean
  evaluation, and it takes a year to produce a one-year result.

## Addresses

Flaw **A** (backtest contamination — called the biggest flaw in
`archive/plan.txt`) and part of **E**.
