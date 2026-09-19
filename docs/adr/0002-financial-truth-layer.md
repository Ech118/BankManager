# ADR 0002 — A financial truth layer with provenance

**Status:** accepted (Step 0)

## Context

Research output is only as trustworthy as its weakest number, and a reader
cannot tell which number that is. In a generated report, a figure read from a
10-K and a figure the model half-remembered look identical.

The original design asked agents to label numbers FACT / ESTIMATE / ASSUMPTION
in their prose. That relies on the model classifying honestly and consistently,
which is exactly the property under question.

## Decision

**Every number lives in a normalized facts store with provenance, and agents
cite `fact_id`s, never bare numbers.**

- `FinancialFact` carries the accession, the filing date, the retrieval
  timestamp, the XBRL concept that actually matched, and the source kind.
- Derived facts require a `Derivation` — the formula and the input `fact_id`s.
  A computed number with no lineage cannot be constructed.
- `Claim` rejects a number that cites no `fact_id` and appears in no evidence
  quote.
- Restatements set `superseded_by` rather than overwriting.

Enforced by model validators, so the rules hold regardless of what any prompt
says.

## Consequences

**Good**

- Provenance is structural, not editorial. `type: fact` is assigned by the code
  path a number took, not by a model's self-report.
- The verifier can check things: `unresolved_fact`, `recompute_mismatch` and
  `superseded_fact` are all only possible because facts have identity.
- The report can colour-code honestly.
- Restatement history is preserved, which is what makes point-in-time queries
  possible ([ADR 0003](0003-point-in-time-correctness.md)).

**Costs**

- More verbose than passing floats around.
- Agents must cite, which constrains how they write and occasionally forces a
  claim to be dropped.
- Fact ids must stay stable across runs, so stored reports keep resolving.

## Addresses

Flaws **6** (labels only requested, never enforced) and **I** (unverifiable
qualitative claims) from `archive/plan.txt`.
