"""One module per MCP tool. Specified by docs/mcp-tools.md.

Each module exposes a single `run(request, backends) -> response` function,
validates its arguments with the contract model, and does nothing else. A tool
that starts to contain a formula belongs in calc/ instead (docs/adr/0007).

Nine tools wrap data/. One - calculate_valuation - wraps calc/, and is the only
place mcp_server imports another partition.
"""

from __future__ import annotations

TOOL_MODULES: tuple[str, ...] = (
    "search_filings",
    "get_filing_section",
    "search_filing",
    "get_financial_facts",
    "get_market_snapshot",
    "get_company_profile",
    "get_peer_companies",
    "search_news",
    "calculate_valuation",
    "resolve_fact",
)
"""The ten tools. Must stay in step with schema.contracts.tools.TOOL_REQUESTS."""
