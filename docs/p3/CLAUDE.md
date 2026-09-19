# P3 — rules

You are working in **P3 (Agents, orchestrator & web)**. Root rules:
[CLAUDE.md](../../CLAUDE.md).

## Boundaries

**May edit:** `agents/`, `prompts/`, `orchestrator/`, `web/`, `tests/e2e/`,
`docs/p3/`
**May add (never edit) files in:** `docs/requests/`
**Everything else is read-only**, including `schema/`, `fixtures/mock/`,
`tests/contracts/`, and the other partitions' directories.

**May import:** `schema.contracts`
**May NOT import:** `data/`, `calc/`, `audit/`, `mcp_server/`

Everything reaches P3 through MCP tools. That is the boundary
([ADR 0007](../adr/0007-partition-boundaries.md)).

## Never implement outside your partition

If you need something from P1 or P2, add a file to `docs/requests/` and keep
working against the mock. Do not patch their code — file a request with a
minimal repro.

## Never change `schema/` without a CONTRACT-CHANGE PR

Approval from all three partitions plus a `schema/CHANGELOG.md` entry. As
coordinator you *apply* approved changes — you do not originate them unilaterally
([CONTRIBUTING.md](../../CONTRIBUTING.md)).

## P3-specific rules

- **Agents do not do arithmetic.** Every number comes from a `fact_id` or from
  `calculate_valuation`.
- **Mock mode speaks real MCP.** Use the SDK's in-memory transport. Do not add a
  shortcut to `data.api` — a boundary exercised only in production is untested.
- **Apply `redact` centrally**, before any agent call.
- **Give the Red Team the raw fact sheet**, not just the analysts' summaries.
- **The Synthesizer emits no numbers** and renders no document. Its verdict word
  must satisfy `validate_consistency`.
- **`report/` is deterministic.** No LLM in the renderer.
- **Unverified claims render with a marker**, never hidden.
- **The disclaimer appears on every page.** There is a test.
- **Shared prompt rules live in `prompts/shared_rules.md`**, never duplicated
  per agent.
- **Findings without evidence are dropped and logged**, never silently.
- **Invalid agent output is retried once, then fails loudly** with the raw text
  logged.

## Coordinator duties

Until reassigned, P3 also:

- applies approved contract changes to `schema/contracts/`, runs
  `make gen-schema`, regenerates fixtures, and adds the CHANGELOG entry
- runs the [roadmap](../roadmap.md) checkpoints
- triages e2e failures to the producing partition

Coordinator commits touching shared files use
`scripts/check_ownership.sh coordinator`.

## Running tests

```bash
make test-contracts                              # must pass before every commit
python -m pytest agents/tests orchestrator/tests tests/e2e -q
make check-ownership P=p3                        # before every push
cd web && npm run typecheck
```

## Before every commit

1. `git status`, then `git add <your paths>` — never `git add -A`
2. `make lint && make test-contracts`
3. `scripts/check_ownership.sh p3`
4. Commit with a `[p3]` prefix
5. Update [STATUS.md](STATUS.md) when something moves from mock to real
