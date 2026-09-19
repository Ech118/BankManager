# P1 — rules

You are working in **P1 (Data & MCP)**. Root rules: [CLAUDE.md](../../CLAUDE.md).

## Boundaries

**May edit:** `data/`, `mcp_server/`, `fixtures/real/`, `docs/p1/`
**May add (never edit) files in:** `docs/requests/`
**Everything else is read-only**, including `schema/`, `fixtures/mock/`,
`tests/contracts/`, and the other partitions' directories.

**May import:** `schema.contracts`
**May NOT import:** `calc/`, `audit/`, `agents/`, `orchestrator/`

One exception, in one file: `mcp_server/tools/calculate_valuation.py` imports
`calc.api`. It is a pass-through and must hold no formula
([ADR 0007](../adr/0007-partition-boundaries.md)).

## Never implement outside your partition

If you need something from P2 or P3, add a file to `docs/requests/` and keep
working against the mock. Do not patch their code, even to fix an obvious bug —
file a request with a minimal repro.

## Never change `schema/` without a CONTRACT-CHANGE PR

`schema/contracts/` is the source of truth and `schema/*.json` is generated from
it. Changing either needs approval from all three partitions and a
`schema/CHANGELOG.md` entry. See [CONTRIBUTING.md](../../CONTRIBUTING.md).

Changing a `data/api.py` signature is also a contract change —
`tests/contracts/test_signatures.py` will fail if you try.

## P1-specific rules

- **Every read takes an `as_of`.** None means "latest known"; the MCP layer
  always passes one explicitly.
- **Never use `companyfacts` for a historical run.** It returns restated values
  ([ADR 0003](../adr/0003-point-in-time-correctness.md)).
- **A restatement sets `superseded_by`. It never overwrites.**
- **Missing data is `unavailable` plus a `data_quality` gap.** Never `0`, never
  a guess, never a fallthrough to the LLM.
- **Do not compute margins, FCF or ratios.** That is `calc/`.
- **`scale` is provenance only.** `value` is already in full units.
- **All MCP tools are read-only.** Do not add one that writes.
- **`SEC_USER_AGENT` is required.** Fail loudly at startup if it is unset.

## Running tests

```bash
make test-contracts                  # must pass before every commit
python -m pytest data/tests -q       # your unit tests
make check-ownership P=p1            # before every push
```

Live check, once you have keys:

```bash
make check-live BM_TEST_TICKER=MSFT
```

## Before every commit

1. `git status`, then `git add <your paths>` — never `git add -A`
2. `make lint && make test-contracts`
3. `scripts/check_ownership.sh p1`
4. Commit with a `[p1]` prefix
5. Update [STATUS.md](STATUS.md) when something moves from mock to real
