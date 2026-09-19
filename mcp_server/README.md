# mcp_server/ — P1

**Owner: P1.** Rules: [docs/p1/CLAUDE.md](../docs/p1/CLAUDE.md).

The MCP server P3 talks to. Full tool reference:
[docs/mcp-tools.md](../docs/mcp-tools.md).

## What lives here

Ten read-only tools. Nine are thin wrappers over `data/api.py`. One —
`calculate_valuation` — is a thin wrapper over `calc/api.py`.

**No formulas.** If arithmetic appears in a tool module, it belongs in `calc/`
instead. That is the rule reviewers should enforce here without discussion.

## The one cross-partition import

`mcp_server/tools/calculate_valuation.py` imports `calc.api` (P2). It is the
only sanctioned cross-partition import in the repo, recorded in
[ADR 0007](../docs/adr/0007-partition-boundaries.md). It exists because agents
must not do arithmetic, and MCP is the only surface agents can reach — so
exactly one compute tool has to sit on it.

## Transport

| Mode | Transport | Who starts it |
|---|---|---|
| `MODE=live` | stdio | the orchestrator spawns `python -m mcp_server.server` |
| `MODE=mock`, tests | the MCP SDK's in-memory transport | in-process |

Mock mode speaks real MCP rather than shortcutting to `data.api`, so the
boundary is exercised in both modes.

## Read-only, on purpose

There is no tool that writes anything. Filing and news text reaching an agent is
untrusted input; an agent that can only read cannot be talked into damage by
text it found in a filing.
