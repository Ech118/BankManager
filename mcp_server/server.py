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

WHY THE LOW-LEVEL Server
    A tool's advertised inputSchema is generated straight from its contract
    model in schema/contracts/tools.py, and the same model validates the
    incoming arguments. Deriving the schema from a hand-written python
    signature instead would let the two drift apart silently, which is the one
    failure an agent cannot diagnose from the other side of the protocol.

ERRORS
    A tool that fails returns an MCP result with isError set, carrying a
    readable message - it does not raise through the protocol. Agents can read
    a failed result; a transport-level exception just aborts their turn.
    ValueError = out of scope, KeyError = unknown id (docs/mcp-tools.md).

TODO(roadmap Step 3, P1): add search_filings, get_filing_section, search_filing.
TODO(roadmap Step 4, P1): add search_news and calculate_valuation.
"""

from __future__ import annotations

import json
from typing import Any

import mcp_types as types
from mcp.server.lowlevel import Server

from schema.contracts.tools import TOOL_REQUESTS, TOOL_RESPONSES

from .tools import (
    get_company_profile,
    get_financial_facts,
    get_market_snapshot,
    get_peer_companies,
    resolve_fact,
)

SERVER_NAME = "bankmanager-financial-research"

_RUNNERS: dict[str, Any] = {
    "get_financial_facts": get_financial_facts.run,
    "get_market_snapshot": get_market_snapshot.run,
    "get_company_profile": get_company_profile.run,
    "get_peer_companies": get_peer_companies.run,
    "resolve_fact": resolve_fact.run,
}

IMPLEMENTED_TOOLS: tuple[str, ...] = tuple(_RUNNERS)
"""The tools this server currently serves.

The contracts describe all ten (schema.contracts.tools.TOOL_REQUESTS); these are
the ones with an implementation behind them. Advertising a tool that raises
NotImplementedError would be worse than not advertising it - an agent would
plan around a capability that does not exist.
"""

_DESCRIPTIONS: dict[str, str] = {
    "get_financial_facts": (
        "Reported and derived financial facts for a ticker, newest first. Each fact "
        "carries a fact_id to cite. Returns only what was filed on or before as_of; "
        "restated values are excluded unless include_superseded is true. An unknown "
        "metric yields no rows rather than an error."
    ),
    "get_market_snapshot": (
        "Price, shares outstanding and the enterprise-value bridge for a ticker, all "
        "observed at one instant, so a price and a share count can never be mixed "
        "across moments. Null when no snapshot had been observed by as_of."
    ),
    "get_company_profile": (
        "Company identity, SIC classification and fiscal year end. The fiscal year "
        "end decides how periods are labelled and how Q4 is derived."
    ),
    "get_peer_companies": (
        "Comparable companies by SIC code and market-cap band, each with a "
        "selection_reason. Fewer peers than limit is a valid answer."
    ),
    "resolve_fact": (
        "Turn a fact_id back into the fact. Returns the fact even when it was "
        "restated or post-dates as_of, flagging each case separately, so a verifier "
        "can tell 'does not exist' from 'was corrected' from 'not filed yet'."
    ),
}


def _error(message: str) -> types.CallToolResult:
    """A failed tool call the agent can actually read."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], isError=True
    )


def build_server(backend: Any = None) -> Server:
    """Construct the MCP server with the implemented tools registered.

    `backend` is a Backends bundle from mcp_server.backends. Injecting it is
    what lets the same server serve fixtures or Postgres unchanged. It is
    resolved lazily so that importing this module never touches a fixture file
    or a database.
    """
    backends = backend

    def _backends() -> Any:
        nonlocal backends
        if backends is None:
            from .backends import build_backends

            backends = build_backends()
        return backends

    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=name,
                    description=_DESCRIPTIONS[name],
                    inputSchema=TOOL_REQUESTS[name].model_json_schema(),
                    outputSchema=TOOL_RESPONSES[name].model_json_schema(),
                )
                for name in IMPLEMENTED_TOOLS
            ]
        )

    async def on_call_tool(ctx: Any, params: Any) -> types.CallToolResult:
        name = params.name
        runner = _RUNNERS.get(name)
        if runner is None:
            known = ", ".join(IMPLEMENTED_TOOLS)
            return _error(f"Unknown tool {name!r}. This server exposes: {known}.")

        try:
            request = TOOL_REQUESTS[name].model_validate(params.arguments or {})
        except Exception as exc:
            return _error(f"Invalid arguments for {name}: {exc}")

        try:
            response = runner(request, _backends())
        except ValueError as exc:  # out of scope - the reason reaches the UI
            return _error(str(exc))
        except KeyError as exc:  # unknown id
            return _error(f"Not found: {exc}")
        except NotImplementedError as exc:
            return _error(f"{name} is not implemented yet: {exc}")

        payload = response.model_dump(mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, indent=2))],
            structuredContent=payload,
        )

    return Server(
        SERVER_NAME,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def tool_names() -> list[str]:
    """The ten tool names the contracts describe."""
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
    import anyio
    from mcp.server.stdio import stdio_server

    async def main() -> None:
        server = build_server()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    anyio.run(main)


if __name__ == "__main__":
    serve_stdio()
