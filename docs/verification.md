# Verification

Every check, whether it is deterministic or needs an LLM, and where a failure
gets routed.

Implemented by `audit/` (P2). Routing executed by `orchestrator/retry.py` (P3).

---

## The principle

**The gate is mostly deterministic code, plus LLM checks only for qualitative
claims.** ([ADR 0005](adr/0005-deterministic-verification-gate.md))

Seven of the eight checks are pure code. Only `unsupported_claim` needs a model,
and it tries a free string match first.

The reason to keep that list at one entry: a verifier that hallucinates is worse
than no verifier. A missing check leaves a claim unchecked, which is bad. A
hallucinating check stamps a bad claim as *verified*, which is worse — it
converts an unchecked assertion into one the reader has been told is reliable.

---

## The checks

### Deterministic (seven)

| Check | What it catches | Severity |
|---|---|---|
| `unresolved_fact` | a cited `fact_id` that does not exist | error |
| `recompute_mismatch` | a derived number that does not re-derive from its inputs | error |
| `prose_number_mismatch` | the sentence disagrees with its own `ValueObject` | error |
| `superseded_fact` | a figure a later filing restated | error |
| `future_fact` | a fact filed after the run's `as_of` | error |
| `adjusted_as_gaap` | a non-GAAP figure presented as GAAP | warn |
| `cross_agent_contradiction` | two sections asserting incompatible things | warn |

Notes on the less obvious ones:

**`recompute_mismatch`** is possible only because `calc/` is pure and every
derived value carries its formula and inputs. The verifier re-derives the number
independently and compares. This is the check that makes "code computes" load-
bearing rather than aspirational.

**`prose_number_mismatch`** catches the common failure where an agent computes
correctly and then rounds or mistypes the number in the sentence a human
actually reads.

**`future_fact`** is what the backtest's integrity rests on. A single fact from
after the cutoff invalidates the run.

**`cross_agent_contradiction`** exists because the financial and business agents
run in parallel and cannot see each other. This is where "the moat is durable"
and "pricing power is eroding" get caught sitting in the same report.

### LLM (one)

| Check | What it catches | Severity |
|---|---|---|
| `unsupported_claim` | a qualitative claim the cited passage does not support | error |

Procedure:

1. Whitespace-normalised **verbatim substring match** of the quote in the cited
   section. Most claims settle here, for free.
2. Only if that fails, and only if a `verify_claim` callable was supplied, ask a
   model whether the passage still supports a faithful paraphrase.
3. With no `verify_claim`, a failed match is reported as unsupported — the safe
   direction, since the alternative is passing an unchecked claim.

The prompt (`prompts/verifier.md`) biases toward `not_supported`. A false
positive costs one retry; a false negative reaches the reader with a
verification stamp it did not earn.

---

## Retry routing table

Every section has exactly one owning agent (`schema/contracts/state.py`
`SECTION_OWNERS`), so every failed claim has exactly one address.

| Section | Owner |
|---|---|
| `company`, `management`, `competitive_position`, `catalysts` | `business` |
| `financials`, `balance_sheet`, `cash_flow`, `earnings_quality` | `financial` |
| `valuation`, `expectations` | `valuation` |
| `scenarios`, `sp500_comparison` | `scenario` |
| `risks` | `red_team` |
| `decision` | `synthesizer` |

### Retryable vs not

| Issue type | Retryable | Why |
|---|---|---|
| `unresolved_fact` | yes | the agent can cite a real fact |
| `prose_number_mismatch` | yes | the agent can restate it correctly |
| `superseded_fact` | yes | the agent can cite the current fact |
| `adjusted_as_gaap` | yes | the agent can label it correctly |
| `unsupported_claim` | yes | the agent can find a real quote or drop the claim |
| `cross_agent_contradiction` | yes | the owning agent can reconcile or qualify |
| `recompute_mismatch` | **no** | `calc/` and the stored value disagree — a code bug |
| `future_fact` | **no** | `data/` served something it should not have |

The two non-retryable types escalate to a human. Re-prompting an agent cannot
fix a bug in the code below it, and retrying would just burn tokens on a
guaranteed failure.

### The cap

**Two attempts per section.** An agent that has failed the same check twice will
not pass on the third try, and a pipeline that retries indefinitely has no
worst-case latency.

One directive per section, not per issue: an agent redoing a section should see
every problem with it at once.

### After the cap

The report **ships**, with the failing claims marked `unverified` and rendered
with a visible marker.

This is deliberate. The alternatives are worse:

- **Block the report** — the reader gets nothing because one quote out of forty
  could not be matched.
- **Drop the claims silently** — the reader cannot tell a fully checked report
  from one that quietly lost its weakest claims.

A labelled unverified claim is honest. `VerificationResult.claims_unverified`
carries the count, and the report states it.

---

## What `audit/` is allowed to touch

Reads a `ResearchState` and a `Factsheet`. Nothing else.

Both external needs are **injected**:

- `get_text` — `data.api.get_section_text`, so `audit/` never imports `data/`
- `verify_claim` — an LLM callable, so `audit/` depends on no model SDK

That is what keeps the entire gate testable with two stubs, and it is why
`audit/` can live in P2 without creating a dependency on P1 or P3.
