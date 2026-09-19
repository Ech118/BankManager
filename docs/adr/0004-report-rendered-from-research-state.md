# ADR 0004 — The report is rendered from ResearchState

**Status:** accepted (Step 0)

## Context

The natural design is to let the final agent write the report: it has read
everything, and models write fluent prose.

The problem is that fluent prose is unverifiable. A synthesizer writing fifteen
sections will introduce numbers nobody checked, restate claims in stronger terms
than the evidence supports, and smooth over contradictions between sections —
all while sounding more authoritative than the material underneath it.

Checking the output afterwards does not work either: by then the claims are
sentences, not structures, and matching a sentence back to the evidence is the
hard problem all over again.

## Decision

**The report is rendered from a structured `ResearchState` object, never from
free-form agent text.**

- Agents write `Claim`s into the one section they own.
- `orchestrator/report/generator.py` renders a `Verdict` deterministically. No
  LLM in the renderer.
- Every sentence a reader sees traces to a `Claim`; every `Claim` has been
  through the verification gate.
- Unverified claims are rendered **with a marker**, never dropped.

The Synthesizer survives this, with a narrower job: the thesis, answering the
Red Team, choosing the primary catalyst and biggest risk, the $10,000 answer,
and reconciling contradictions. All of that lands in `ResearchState.decision` as
claims. It writes no numbers and renders no document.

## Consequences

**Good**

- Nothing unverified reaches the reader unlabelled.
- The report is a pure function of the state: same state, same bytes. Two runs
  can be diffed meaningfully.
- The UI and the markdown report are two renderings of one object, and cannot
  disagree.
- Cheap to add a format later.

**Costs**

- Reports read more mechanically than agent-written prose. That is the trade:
  fluency for checkability.
- Every report improvement is a template or generator change, not a prompt
  tweak.
- `ResearchState` is now a schema that has to be versioned (`STATE_VERSION`).

## Addresses

Flaw **7** (verdict buried last, sections overlapping) and the delivery half of
**I** (unverifiable claims) from `archive/plan.txt`.
