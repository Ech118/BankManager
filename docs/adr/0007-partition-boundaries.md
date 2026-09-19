# ADR 0007 — Three partitions, and exactly one exception

**Status:** accepted (Step 0)

## Context

Three people build this repo simultaneously, each with their own Claude
instance. Two failure modes to avoid:

- **Text conflicts** — two people editing the same file. Solved by disjoint
  ownership.
- **Integration conflicts** — everything merges cleanly and the pieces do not
  fit. A field renamed, a percent where a fraction was expected, a function
  returning a different shape than its caller assumed. Not solved by ownership;
  solved by frozen contracts, mocks that exist from day one, and contract tests.

## Decision

| Partition | Owns | Produces |
|---|---|---|
| **P1** Data & MCP | `data/`, `mcp_server/`, `fixtures/real/` | the fact sheet |
| **P2** Calc, audit & eval | `calc/`, `audit/`, `backtest/`, `predictions/` | metrics, scenario results, audit |
| **P3** Agents, orchestrator & web | `agents/`, `prompts/`, `orchestrator/`, `web/`, `tests/e2e/` | analyses, verdict, UI |

`schema/` is shared and changes only by CONTRACT-CHANGE PR with all three
approvals.

**Import rules**

- Every partition may import `schema.contracts`.
- P3 reaches data **only through MCP tools**. It imports neither `data/` nor
  `calc/`.
- `calc/` is pure: no network, no database, no LLM.
- `audit/` reads a `ResearchState` and a `Factsheet` only; `get_text` and
  `verify_claim` are injected.
- P1 knows nothing about agents.

### The one exception

`mcp_server/tools/calculate_valuation.py` (P1) imports `calc.api` (P2).

It exists because [ADR 0001](0001-code-computes-llm-interprets.md) says agents
must not do arithmetic, and MCP is the only surface agents can reach — so
exactly one compute tool has to sit on it. The alternatives were worse:
duplicating formulas into P1 (two implementations that drift), or letting P3
import `calc/` (a far wider breach than one wrapper).

It is safe because it is a **pass-through**. Arithmetic appearing in that file
is a defect; it belongs in `calc/`. Reviewers should treat it as one without
discussion.

This is the **only** sanctioned cross-partition import. Adding a second needs a
new ADR.

### P3 speaks MCP in both modes

`orchestrator/mcp_client.py` uses the MCP SDK's in-memory transport for mock
mode and tests, and stdio for live. Mock mode deliberately does not shortcut to
`data.api`: a boundary exercised only in production is a boundary nobody has
tested.

## Consequences

**Good**

- Ownership is mechanically checkable (`scripts/check_ownership.sh`).
- Mock mode means nobody waits: P3 builds the whole UI against ACME on day one.
- Contract tests catch integration drift at commit time, not at integration
  time.
- Swapping a backend changes one composition root.

**Costs**

- Indirection. P3 cannot call a Python function directly even when that would be
  simpler.
- Every cross-partition change needs a request file and three approvals.
- `mcp_server/` sits in P1 but serves a tool implemented by P2, which is a
  genuine wrinkle in an otherwise clean map.

## Addresses

The partition plan from `archive/plan.txt` §15, with the ownership map and
change protocol carried forward into `CONTRIBUTING.md` and `CLAUDE.md`.
