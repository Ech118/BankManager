# audit/ — P2 Verification Gate

**Owner: P2.** Rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).

The gate between the agents and the reader. Full check list and routing table:
[docs/verification.md](../docs/verification.md).

## Public interface

```python
run_audit(state, factsheet, get_text, verify_claim=None) -> VerificationResult
```

Reads a `ResearchState` and a `Factsheet`, **and nothing else**. Both external
needs are injected:

- `get_text` — `data.api.get_section_text`, so `audit/` never imports `data/`
- `verify_claim` — an LLM callable, so `audit/` depends on no model SDK

That injection is what keeps the whole gate testable with two stubs.

## Mostly deterministic

Seven of the eight checks are pure code
([ADR 0005](../docs/adr/0005-deterministic-verification-gate.md)):

| Check | Catches |
|---|---|
| `unresolved_fact` | a cited `fact_id` that does not exist |
| `recompute_mismatch` | a number that does not re-derive from its inputs |
| `prose_number_mismatch` | the sentence disagrees with the value object |
| `superseded_fact` | a figure a later filing restated |
| `future_fact` | a fact filed after the run's `as_of` |
| `adjusted_as_gaap` | a non-GAAP figure presented as GAAP |
| `cross_agent_contradiction` | two sections asserting incompatible things |

Only **`unsupported_claim`** needs an LLM, and it tries a verbatim string match
first. Keeping that list at one entry is deliberate: a verifier that
hallucinates is worse than none, because it launders a bad claim as checked.

## Failure is not fatal

A failed claim routes a `RetryDirective` to the one agent that owns its section,
capped at two attempts. After the cap the report **ships** with those claims
marked `unverified` — visible and labelled, rather than blocked or silently
dropped.

Two issue types are never retried: `recompute_mismatch` (a bug in `calc/`) and
`future_fact` (a bug in `data/`). Re-prompting an agent cannot fix either.
