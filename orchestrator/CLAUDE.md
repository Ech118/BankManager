# orchestrator/ — P3

You are working in **P3**. Full rules: [docs/p3/CLAUDE.md](../docs/p3/CLAUDE.md).

- **May import:** `schema.contracts`, `agents/`
- **May NOT import:** `data/`, `calc/`, `audit/`, `mcp_server/`
- **Public interface:** `orchestrator/api.py`. Changing a signature is a
  CONTRACT-CHANGE PR.

`mcp_client.py` is the only door to data, and it speaks real MCP in **both**
modes. Do not add a mock-mode shortcut to `data.api`: the boundary would then
only be exercised in production.

Apply the `redact` hook centrally, before any agent call. Give the Red Team the
raw fact sheet, not just the other agents' summaries.

`report/` is deterministic. No LLM belongs in the renderer.
