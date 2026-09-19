# calc/ — P2

You are working in **P2**. Full rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).

- **May edit:** `calc/`, `audit/`, `backtest/`, `predictions/`, `docs/p2/`
- **May import:** `schema.contracts` only
- **May NOT import:** `data/`, `agents/`, `orchestrator/`, `mcp_server/`
- **Public interface:** `calc/api.py`. Changing a signature is a
  CONTRACT-CHANGE PR.

**`calc/` is pure.** No network, no database, no LLM — ever. That is what makes
`audit/`'s recompute check meaningful.

**No function takes both a factsheet and an `as_of`.** The factsheet's `as_of`
is authoritative.

The scenario weight band and the prior cap live in `config.py`. They are the
bounds on the LLM; do not make them reachable from a prompt.
