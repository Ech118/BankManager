# data/ — P1

You are working in **P1**. Full rules: [docs/p1/CLAUDE.md](../docs/p1/CLAUDE.md).

- **May edit:** `data/`, `mcp_server/`, `fixtures/real/`, `docs/p1/`
- **May import:** `schema.contracts` only
- **May NOT import:** `calc/`, `audit/`, `agents/`, `orchestrator/`
- **Public interface:** `data/api.py`. Changing a signature is a
  CONTRACT-CHANGE PR.

Every read takes an `as_of`. Never use `companyfacts` for a historical run — it
returns restated values ([docs/sec-pitfalls.md](../docs/sec-pitfalls.md)).

Do **not** compute margins, FCF or ratios. That is `calc/`.
