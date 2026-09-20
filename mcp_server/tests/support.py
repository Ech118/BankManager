"""Shared helpers for the MCP server tests.

Every helper here goes over the MCP SDK's in-memory transport: a real client, a
real server, real tool dispatch and real argument validation. Nothing calls
`data.api` directly.

That is the point. If these tests shortcut to Python function calls, the wiring
P3 actually depends on would only ever be exercised in production
(docs/adr/0007-partition-boundaries.md).
"""

from __future__ import annotations

import anyio
from mcp import Client

from mcp_server.server import build_server

TICKER = "ACME"

LATEST = "2026-09-19"
"""The fixture's own as_of: everything is visible."""

BEFORE_FY2025_10K = "2025-06-01"
"""After the FY2024 10-K (filed 2025-02-21), before the FY2025 10-K
(filed 2026-02-20). The FY2025 filing and all five of its sections are
invisible at this date."""


def call(tool: str, arguments: dict):
    """Call one tool over the in-memory transport and return the CallToolResult."""

    async def go():
        async with Client(build_server()) as client:
            return await client.call_tool(tool, arguments)

    return anyio.run(go)


def ok(tool: str, arguments: dict) -> dict:
    """Call a tool, assert it succeeded, and return its structured content."""
    result = call(tool, arguments)
    detail = result.content[0].text if result.content else ""
    assert not result.is_error, f"{tool} failed: {detail}"
    assert result.structured_content is not None, f"{tool} returned no structured content"
    return result.structured_content


def error_text(tool: str, arguments: dict) -> str:
    """Call a tool, assert it FAILED, and return the message the agent would read."""
    result = call(tool, arguments)
    assert result.is_error, f"{tool} unexpectedly succeeded: {result.structured_content}"
    return result.content[0].text if result.content else ""


def list_tool_names() -> list[str]:
    async def go():
        async with Client(build_server()) as client:
            return [t.name for t in (await client.list_tools()).tools]

    return anyio.run(go)
