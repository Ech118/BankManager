# schema/ — shared contracts

**Owned jointly by P1, P2 and P3.** Changing anything here is a
CONTRACT-CHANGE PR: approval from all three partitions plus a
[CHANGELOG.md](CHANGELOG.md) entry
([CONTRIBUTING.md](../CONTRIBUTING.md#contract-change-process)).

## Source of truth

```
schema/contracts/*.py     pydantic models  <- AUTHORITATIVE, edit these
schema/*.json             JSON Schema      <- GENERATED, never hand-edit
```

Regenerate with:

```bash
make gen-schema
```

`tests/contracts/test_schema_export.py` regenerates in memory and compares byte
for byte with what is committed, so the two cannot drift silently.

## Why commit the generated JSON at all

`web/` is TypeScript and cannot import pydantic. The committed schemas are what
a non-Python consumer reads, and what the jsonschema-based contract tests
validate fixtures against — so the JSON is exercised, not just the models.

## Layout

| File | Contents |
|---|---|
| `contracts/enums.py` | closed vocabularies, including `Horizon` |
| `contracts/common.py` | `ValueObject`, `Evidence`, id types |
| `contracts/facts.py` | `FinancialFact`, `Derivation` |
| `contracts/filings.py` | `Filing`, `FilingSection` |
| `contracts/market.py` | `MarketSnapshot`, `CompanyProfile`, `Peer`, `NewsItem` |
| `contracts/claims.py` | `Claim` |
| `contracts/factsheet.py` | `Factsheet` (P1's output) |
| `contracts/metrics.py` | `Metrics` (P2's output) |
| `contracts/analysis.py` | `Analysis` (one agent's output) |
| `contracts/scenarios.py` | `Scenarios` (the LLM's proposal) |
| `contracts/scenario_result.py` | `ScenarioResult`, `ScenarioWeights`, `Prior` |
| `contracts/state.py` | `ResearchState` and the fourteen sections |
| `contracts/verification.py` | `VerificationResult`, `RetryDirective` |
| `contracts/verdict.py` | `Verdict` (the finished report) |
| `contracts/tools.py` | the ten MCP tool request/response pairs |
| `contracts/interfaces.py` | repository and MCP client Protocols |
| `contracts/export.py` | the generator |

## The rules that live here rather than in a code review

- `ValueObject`'s four conditional rules — `ok` needs a number, `ok` needs
  provenance, `unavailable` needs null, fractions are not percents.
- A derived fact requires a `Derivation`; nothing else may carry one.
- A `Claim` with a number must cite a `fact_id` or quote it.
- A scenario weight clamp must be recorded — a flag that disagrees with the
  numbers is rejected.
- Every data tool request requires an `as_of`.
- A section's owner must match `SECTION_OWNERS`.

Each is enforced by a model validator **and** covered by a test in
`tests/contracts/`.

## Versioning

`SCHEMA_VERSION` (contract set) and `STATE_VERSION` (the `ResearchState` shape)
move independently. Additive changes bump the minor version; renames, removals
and retypes are breaking and bump the major.

Consumers must tolerate unknown extra fields — every artifact model sets
`extra="allow"`, so an additive change never breaks an older reader.
