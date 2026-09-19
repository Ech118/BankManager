# ADR 0005 — A mostly deterministic verification gate

**Status:** accepted (Step 0)

## Context

Something has to check the output before a reader sees it. The obvious approach
is an LLM auditor that reads the report and flags problems.

That has a specific failure mode which is worse than having no auditor: **a
verifier that hallucinates launders bad claims.** An unchecked claim is at least
honestly unchecked. A claim stamped "verified" by a model that did not really
verify it has been converted into something the reader has been told to trust.

An LLM auditor is also expensive, slow, and non-reproducible — so a claim can
pass on Monday and fail on Tuesday with no change to the input.

## Decision

**The verification gate is mostly deterministic code, plus LLM checks only for
qualitative claims. Retries are targeted to the owning section and capped; after
the cap, the report ships with failed claims marked unverified.**

Seven deterministic checks: `unresolved_fact`, `recompute_mismatch`,
`prose_number_mismatch`, `superseded_fact`, `future_fact`, `adjusted_as_gaap`,
`cross_agent_contradiction`.

One LLM check: `unsupported_claim` — and it attempts a verbatim string match
first, consulting a model only when that fails.

`audit/` reads a `ResearchState` and a `Factsheet` and nothing else. `get_text`
and `verify_claim` are injected callables, so it imports neither `data/` nor any
model SDK, and the whole gate is testable with two stubs.

**Retry:** each section has one owning agent, so each failure has one address.
Max two attempts. Two issue types are never retried — `recompute_mismatch` (a
`calc/` bug) and `future_fact` (a `data/` bug) — because re-prompting an agent
cannot fix code below it.

**After the cap the report ships**, with failing claims marked `unverified` and
rendered with a visible marker.

## Consequences

**Good**

- Most failures are caught by code that is fast, free and reproducible.
- The one LLM check is small enough to audit, prompt carefully, and run on a
  cheaper model.
- Targeted retries keep cost bounded: one agent, one section, not seven calls.
- A run always terminates. Worst-case latency is knowable.

**Costs**

- Deterministic checks catch only what can be specified. A claim that is
  well-sourced and wrong passes.
- Shipping with unverified claims means the reader must read the markers. We
  judged a labelled flaw better than a blocked report or a silently dropped
  claim.
- `cross_agent_contradiction` is hard to do well in pure code and starts narrow.

## Addresses

Flaws **9** (no validation), **I** (unverifiable claims) and **K** (cost and
latency) from `archive/plan.txt`.
