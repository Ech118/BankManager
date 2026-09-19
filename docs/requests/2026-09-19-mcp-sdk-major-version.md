# P3 -> P1 / coordinator: the repo is on two MCP SDK majors

**From:** P3  **To:** P1 (`mcp_server/`), coordinator  **Urgency:** medium: it breaks CI and blocks integration.

## What happened

- `mcp_server/requirements.txt` says `mcp>=1.2` (unbounded, so it installs **2.x** today) and P1's new
  `mcp_server/tests/test_tools_mock.py` uses the **2.x** API (`from mcp import Client`).
- P3 was written against **1.x** (`FastMCP`, `create_connected_server_and_client_session`) and pinned `mcp<2`,
  because installing 2.x into an environment with an older FastAPI broke `starlette`.

Both cannot live in one environment.

## What P3 verified (so this needn't block anyone)

- **A clean environment with `mcp 2.2` + `fastapi 0.141` + `starlette 1.6` resolves with no conflicts.** The clash was an
  old FastAPI (0.115), not `mcp` 2.x itself.
- P3's MCP client and test double now support **both** majors (`orchestrator/mcp_client.py::sdk_client_class`, the
  version-specific bits are confined there). The whole P3 suite (137 tests, including the stdio transport) passes on
  **mcp 1.30 and mcp 2.2**, each in its own environment.

## Recommendation

Standardise on **mcp 2.x** (P1's direction, and the current line): `mcp>=2,<3` in `mcp_server/requirements.txt`, and
`fastapi>=0.141` for P3. P3 needs no code change for that. Tell P3 if you would rather pin 1.x instead; that is also fine
for P3, but P1's tests would then need `FastMCP` and `create_connected_server_and_client_session`.

## Two things P1 must know about mcp 2.x

1. **Tool error messages are masked.** A tool that raises `ValueError("Banks are out of scope for v1.")` reaches the client
   as just `Error executing tool <name>`. The out-of-scope reason has to reach the user, so P1's tools must raise the SDK's
   `ToolError` (`mcp.server.mcpserver.exceptions.ToolError`; in 1.x `mcp.server.fastmcp.exceptions.ToolError`) with the
   human-readable reason. P3's test double does this (`tests/e2e/support/fake_mcp.py`).
2. **Result fields are snake_case in 2.x** (`structured_content`, `is_error`) and camelCase in 1.x. A tool returning `-> dict`
   yields text JSON with `structured_content` unset in 2.x; P3 handles both.

## Also

`make lint` (and CI's `ruff check .`) currently fails on `main`: `mcp_server/tests/conftest.py:7` has an unused
`import os` (F401). P3 did not touch P1's files.
