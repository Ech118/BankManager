# P2 — rules

You are working in **P2 (Calc, audit & eval)**. Root rules:
[CLAUDE.md](../../CLAUDE.md).

## Boundaries

**May edit:** `calc/`, `audit/`, `backtest/`, `predictions/`, `docs/p2/`
**May add (never edit) files in:** `docs/requests/`
**Everything else is read-only**, including `schema/`, `fixtures/mock/`,
`tests/contracts/`, and the other partitions' directories.

**May import:** `schema.contracts`
**May NOT import:** `data/`, `mcp_server/`, `agents/`, `orchestrator/`

`backtest/` may import `orchestrator.api` — it drives full runs through the same
entry point a live run uses.

## Never implement outside your partition

If you need something from P1 or P3, add a file to `docs/requests/` and keep
working against the mock. Do not patch their code — file a request with a
minimal repro.

## Never change `schema/` without a CONTRACT-CHANGE PR

Approval from all three partitions plus a `schema/CHANGELOG.md` entry. See
[CONTRIBUTING.md](../../CONTRIBUTING.md). Changing a `calc/api.py` or
`audit/api.py` signature is a contract change, and
`tests/contracts/test_signatures.py` will fail if you try.

## P2-specific rules

- **`calc/` is pure.** No network, no database, no LLM — ever. That is what
  makes `audit/`'s recompute check possible.
- **No function takes both a factsheet and an `as_of`.** The factsheet's `as_of`
  is authoritative.
- **`audit/` reads a `ResearchState` and a `Factsheet` only.** `get_text` and
  `verify_claim` are injected; do not replace either with a direct import.
- **Keep the LLM check list at one entry.** A verifier that hallucinates is
  worse than none ([ADR 0005](../adr/0005-deterministic-verification-gate.md)).
- **A missing input yields `unavailable`, never `0`.**
- **Never inflate a score.** The rubric is a fixed table in `config.py`.
- **A clamp is always recorded.** A weight silently altered is a bug, and the
  contract rejects it.
- **The prior shifts are summed before the cap applies**, so two agents cannot
  exceed it by splitting a request.
- **`predictions/` is append-only.** Never edit a recorded prediction.
- **Backtest grading uses excess return over the index**, never absolute return.

## Running tests

```bash
make test-contracts                        # must pass before every commit
python -m pytest calc/tests audit/tests -q # your unit tests
make check-ownership P=p2                  # before every push
```

## Before every commit

1. `git status`, then `git add <your paths>` — never `git add -A`
2. `make lint && make test-contracts`
3. `scripts/check_ownership.sh p2`
4. Commit with a `[p2]` prefix
5. Update [STATUS.md](STATUS.md) when something moves from mock to real
