## What and why

<!-- One or two sentences. What changed, and what problem it solves. -->

## Partition

<!-- Tick exactly one. A PR spanning two partitions usually should have been a
     request instead (CONTRIBUTING.md). -->

- [ ] P1 — Data & MCP
- [ ] P2 — Calc, audit & eval
- [ ] P3 — Agents, orchestrator & web
- [ ] Contract change (see below)
- [ ] Coordinator / shared

## Checks

- [ ] `make lint` passes
- [ ] `make test-contracts` passes
- [ ] `make check-ownership P=<mine>` passes
- [ ] Unit tests added or updated for the behaviour I changed
- [ ] **`docs/pN/STATUS.md` updated** if this changes what works

> STATUS is how the other two partitions know what they can rely on. A PR that
> moves a capability from mock to real and leaves STATUS stale is incomplete.

## Contract change

- [ ] **This PR changes `schema/`, an `api.py` signature, a Protocol, or an MCP
      tool shape.**

If ticked, all of the following are required
([CONTRIBUTING.md](../CONTRIBUTING.md#contract-change-process)):

- [ ] A request file exists in `docs/requests/` stating what and why
- [ ] **Approval from all three partitions** is recorded in that file
- [ ] `make gen-schema` was run and the generated JSON is committed
- [ ] `make gen-mock` was run and the fixtures are committed
- [ ] `SCHEMA_VERSION` bumped (and `STATE_VERSION` if the state shape moved)
- [ ] `schema/CHANGELOG.md` entry added
- [ ] `tests/contracts/test_signatures.py` updated if a signature moved

## Principles

<!-- Tick any this PR touches, and say how it stays consistent with them.
     Details: docs/adr/ -->

- [ ] Code computes, the LLM interprets — no new arithmetic in an agent
- [ ] Provenance — every new number carries a `fact_id` or a derivation
- [ ] Point-in-time — every new data read takes an `as_of`
- [ ] Report rendered from `ResearchState` — no new free-form prose path
- [ ] Verification — new checks are deterministic unless they genuinely need an LLM
- [ ] Partition boundaries — no new cross-partition import

<!-- Adding a second cross-partition import requires a new ADR (ADR 0007). -->

## Notes for reviewers

<!-- Anything non-obvious: a trade-off you made, something you chose not to do,
     a follow-up you are deliberately deferring. -->
