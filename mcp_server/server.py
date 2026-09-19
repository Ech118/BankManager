"""The financial-research MCP server: registers the ten tools and serves them.

Specified by docs/mcp-tools.md.

TRANSPORT (decision: amendment 3)
  MODE=live           stdio. The orchestrator spawns this module as a subprocess.
  MODE=mock and tests the MCP SDK's IN-MEMORY transport, in-process.

Both are real MCP. Mock mode does not bypass the protocol and call data/
directly, because then the boundary would only be tested in production.

Every tool is READ-ONLY. There is no tool that writes, and there never should
be: an agent that can only read cannot be talked into doing damage by text it
found inside a filing (error F).

TODO(roadmap Step 1, P2/P3 checkpoint): serve get_financial_facts,
get_market_snapshot and resolve_fact from the fixture backend.
TODO(roadmap Step 3, P1): add the search and company tools.
TODO(roadmap Step 4, P1): add market, news and calculate_valuation.
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import TOOL_REQUESTS, TOOL_RESPONSES

SERVER_NAME = "bankmanager-financial-research"


def build_server(backend: Any = None) -> Any:
    """Construct the MCP server with all ten tools registered.

    `backend` is a Backends bundle from mcp_server.backends. Injecting it is
    what lets the same server serve fixtures or Postgres unchanged.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1): register tools on an MCP Server")


def tool_names() -> list[str]:
    """The ten tool names this server exposes."""
    return sorted(TOOL_REQUESTS)


def describe_tool(name: str) -> dict:
    """JSON Schema for one tool's arguments, for the MCP tools/list response.

    Generated from the contracts, so a tool's advertised schema can never drift
    from the model that validates its arguments.
    """
    if name not in TOOL_REQUESTS:
        raise KeyError(name)
    return {
        "name": name,
        "inputSchema": TOOL_REQUESTS[name].model_json_schema(),
        "outputSchema": TOOL_RESPONSES[name].model_json_schema(),
    }


def serve_stdio() -> None:
    """Run the server over stdio. The live-mode entry point."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


if __name__ == "__main__":
    serve_stdio()
