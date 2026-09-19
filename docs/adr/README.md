# Architecture decision records

One per core principle. Each states the context, the decision, and what it costs
— the costs matter as much as the benefits, because a decision recorded only
with its upsides cannot be revisited honestly.

| ADR | Principle |
|---|---|
| [0001](0001-code-computes-llm-interprets.md) | Code computes, the LLM interprets |
| [0002](0002-financial-truth-layer.md) | A financial truth layer with provenance |
| [0003](0003-point-in-time-correctness.md) | Point-in-time correctness |
| [0004](0004-report-rendered-from-research-state.md) | The report is rendered from ResearchState |
| [0005](0005-deterministic-verification-gate.md) | A mostly deterministic verification gate |
| [0006](0006-no-naive-chunk-and-embed-rag.md) | No naive chunk-and-embed RAG |
| [0007](0007-partition-boundaries.md) | Three partitions, and exactly one exception |

## Adding one

New ADRs are numbered sequentially and never edited after acceptance — a
superseded ADR is marked superseded and left in place, with the new one linking
back. The record of why something *was* done is what makes it safe to change.

Adding a second cross-partition import requires a new ADR (0007).
