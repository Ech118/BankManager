# agents/ — P3

You are working in **P3**. Full rules: [docs/p3/CLAUDE.md](../docs/p3/CLAUDE.md).

- **May edit:** `agents/`, `prompts/`, `orchestrator/`, `web/`, `tests/e2e/`,
  `docs/p3/`
- **May import:** `schema.contracts` only
- **May NOT import:** `data/`, `calc/`, `audit/`, `mcp_server/`

Data reaches agents through MCP tools, never by import
([ADR 0007](../docs/adr/0007-partition-boundaries.md)).

Agents do not do arithmetic. Every number comes from a `fact_id` or from
`calculate_valuation`.

Shared rules belong in `prompts/shared_rules.md`, not copied per agent.
