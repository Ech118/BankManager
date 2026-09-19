"""The only door from P3 to the data layer.

Specified by docs/mcp-tools.md and docs/adr/0007.
Implements schema.contracts.interfaces.McpClient.

TRANSPORT (amendment 3)
  MODE=mock, tests  the MCP SDK's IN-MEMORY transport, server in-process
  MODE=live         stdio, server spawned as a subprocess

Both are real MCP. Mock mode deliberately does NOT shortcut to data.api: if it
did, the boundary would only ever be exercised in production, and the first time
anyone found out the wiring was wrong would be during a live run.

Argument validation happens here too, against the contract request models, so a
malformed tool call fails in P3 with a clear message rather than inside P1.

TODO(roadmap Step 1, P3): in-memory transport.
TODO(roadmap Step 3, P3): stdio transport.
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import TOOL_REQUESTS, TOOL_RESPONSES


class InMemoryMcpClient:
    """MCP over the SDK's in-memory transport. Mock mode and every test."""

    def __init__(self, server: Any = None) -> None:
        self.server = server
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate against TOOL_REQUESTS[name], call, validate the response."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def list_tools(self) -> list[str]:
        return sorted(TOOL_REQUESTS)

    def close(self) -> None:
        raise NotImplementedError("TODO(roadmap Step 1, P3)")


class StdioMcpClient:
    """MCP over stdio against a spawned mcp_server process. Live mode."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or ["python", "-m", "mcp_server.server"]
        raise NotImplementedError("TODO(roadmap Step 3, P3)")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("TODO(roadmap Step 3, P3)")

    def list_tools(self) -> list[str]:
        raise NotImplementedError("TODO(roadmap Step 3, P3)")

    def close(self) -> None:
        raise NotImplementedError("TODO(roadmap Step 3, P3)")


def build_client(mode: str | None = None) -> Any:
    """In-memory client in mock mode, stdio client in live mode."""
    raise NotImplementedError("TODO(roadmap Step 1, P3)")


def response_model(name: str):
    """Contract model for one tool's response."""
    return TOOL_RESPONSES[name]
