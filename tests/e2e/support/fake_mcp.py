"""A P3-owned TEST DOUBLE for the MCP server (real MCP protocol, fixture data).

Why it exists: mcp_server/ is P1's and is still a skeleton, but P3's client, agents
and coordinator must be exercised against the real protocol now, not later. This
server speaks genuine MCP (FastMCP) and serves the frozen ACME fixtures through the
contract response models, honouring the two semantics that matter to P3 tests:
POINT-IN-TIME (nothing filed after as_of) and RESTATEMENTS (superseded facts are
excluded unless asked for).

It does NOT import data/, calc/ or mcp_server/. When P1 ships the real server the
same tests can run against it by swapping the injected server object.

Run as a stdio server (used to test StdioMcpClient):
    python -m tests.e2e.support.fake_mcp
"""

from __future__ import annotations

import json
from pathlib import Path

try:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from schema.contracts.enums import ItemCode
from schema.contracts.facts import FinancialFact
from schema.contracts.filings import Filing, FilingSection
from schema.contracts.market import CompanyProfile, MarketSnapshot, Peer
from schema.contracts.metrics import Metrics, ReverseDcf
from schema.contracts.tools import (
    CalculateValuationResponse,
    GetCompanyProfileResponse,
    GetFilingSectionResponse,
    GetFinancialFactsResponse,
    GetMarketSnapshotResponse,
    GetPeerCompaniesResponse,
    ResolveFactResponse,
    SearchFilingsResponse,
)

VALUATION_METHODS = frozenset(
    {"pe", "ev_ebitda", "ev_revenue", "p_fcf", "peer_median", "historical", "reverse_dcf"}
)
MOCK = Path(__file__).resolve().parents[3] / "fixtures" / "mock"


def _load(name: str):
    return json.loads((MOCK / name).read_text(encoding="utf-8"))


def _text_override(tool: str, section_id: str) -> str | None:
    """Hook so tests can poison a section (prompt-injection tests)."""
    return None


def build_fake_server(
    section_text_hook=None, out_of_scope: dict[str, str] | None = None
) -> _Server:
    """`section_text_hook(section_id, text) -> text` lets a test alter filing text.
    `out_of_scope` maps a ticker to the reason the data tools refuse it, as the real server must.

    Errors are raised as ToolError: mcp 2.x MASKS the message of any other exception, so the real
    server's tools must do the same for the out-of-scope reason to reach the user."""
    server = _Server("fake-bankmanager-financial-research")
    refused = out_of_scope or {}

    def refuse_if_out_of_scope(ticker: str) -> None:
        if ticker in refused:
            raise ToolError(refused[ticker])

    facts = [FinancialFact.model_validate(f) for f in _load("facts.json")]
    filings = [Filing.model_validate(f) for f in _load("filings.json")]

    @server.tool()
    def get_financial_facts(
        ticker: str,
        metrics: list[str],
        as_of: str,
        period_type: str | None = None,
        periods: int | None = None,
        include_superseded: bool = False,
    ) -> dict:
        """Reported facts, newest first. Restated values excluded unless asked for."""
        refuse_if_out_of_scope(ticker)
        rows = [
            f
            for f in facts
            if f.company_id == ticker
            and f.metric in metrics
            and (f.filed_at is None or f.filed_at <= as_of)
        ]
        if period_type:
            rows = [f for f in rows if f.period_type.value == period_type]
        if not include_superseded:
            rows = [f for f in rows if f.superseded_by is None]
        rows.sort(key=lambda f: (f.period_end, f.filed_at or ""), reverse=True)
        return GetFinancialFactsResponse(
            facts=rows[:periods] if periods else rows, as_of=as_of
        ).model_dump(mode="json")

    @server.tool()
    def resolve_fact(fact_id: str, as_of: str) -> dict:
        """Turn a fact_id back into the fact, flagging superseded and future facts."""
        fact = next((f for f in facts if f.fact_id == fact_id), None)
        return ResolveFactResponse(
            fact=fact,
            as_of=as_of,
            is_superseded=bool(fact and fact.superseded_by),
            is_future=bool(fact and fact.filed_at and fact.filed_at > as_of),
        ).model_dump(mode="json")

    @server.tool()
    def search_filings(
        ticker: str, as_of: str, forms: list[str] | None = None, limit: int = 20
    ) -> dict:
        """Filings filed on or before as_of, newest first."""
        refuse_if_out_of_scope(ticker)
        rows = [
            f
            for f in filings
            if f.company_id == ticker
            and f.filed_at <= as_of
            and (not forms or f.form.value in forms)
        ]
        rows.sort(key=lambda f: f.filed_at, reverse=True)
        return SearchFilingsResponse(
            filings=rows[:limit], as_of=as_of, truncated=len(rows) > limit
        ).model_dump(mode="json")

    @server.tool()
    def get_filing_section(section_id: str, as_of: str, max_chars: int | None = None) -> dict:
        """One parsed section, verbatim. KeyError for unknown ids or ones filed after as_of."""
        _, accession, name = section_id.split(":", 2)
        filing = next((f for f in filings if f.accession == accession), None)
        if filing is None or section_id not in filing.section_ids or filing.filed_at > as_of:
            raise ToolError(f"unknown section, or filed after as_of: {section_id}")
        text = (MOCK / "sections" / f"{name}.txt").read_text(encoding="utf-8")
        if section_text_hook:
            text = section_text_hook(section_id, text)
        truncated = bool(max_chars and len(text) > max_chars)
        if truncated:
            text = text[:max_chars]
        section = FilingSection(
            section_id=section_id,
            source_id=f"src:edgar:{accession}:{name}",
            accession=accession,
            company_id=filing.company_id,
            form=filing.form,
            fiscal_period=filing.fiscal_period,
            filed_at=filing.filed_at,
            item=ItemCode(name),
            char_start=0,
            char_end=len(text),
            char_count=len(text),
            text=text,
        )
        return GetFilingSectionResponse(
            section=section, as_of=as_of, truncated=truncated
        ).model_dump(mode="json")

    @server.tool()
    def get_market_snapshot(ticker: str, as_of: str) -> dict:
        refuse_if_out_of_scope(ticker)
        snap = MarketSnapshot.model_validate(_load("market_snapshot.json"))
        return GetMarketSnapshotResponse(
            snapshot=snap if snap.ticker == ticker else None, as_of=as_of
        ).model_dump(mode="json")

    @server.tool()
    def get_company_profile(ticker: str, as_of: str) -> dict:
        refuse_if_out_of_scope(ticker)
        prof = CompanyProfile.model_validate(_load("company_profile.json"))
        return GetCompanyProfileResponse(
            profile=prof if prof.ticker == ticker else None, as_of=as_of
        ).model_dump(mode="json")

    @server.tool()
    def get_peer_companies(ticker: str, as_of: str, limit: int = 6) -> dict:
        """The deterministic default peers (SIC + market-cap band), each with a selection reason."""
        refuse_if_out_of_scope(ticker)
        peers = [Peer.model_validate(p) for p in _load("peers.json")][:limit]
        return GetPeerCompaniesResponse(peers=peers, as_of=as_of).model_dump(mode="json")

    @server.tool()
    def calculate_valuation(
        ticker: str,
        methods: list[str],
        peer_tickers: list[str] | None = None,
        assumptions: dict[str, float] | None = None,
    ) -> dict:
        """Stands in for calc/: returns the frozen ACME valuation block and reverse DCF.

        Real calc computes from the chosen methods and peers; this double only records them in
        `notes` so a test can prove what the agent asked for. Unknown methods are refused."""
        refuse_if_out_of_scope(ticker)
        unknown = [m for m in methods if m not in VALUATION_METHODS]
        if unknown:
            raise ToolError(
                f"unknown valuation method(s): {unknown}; use one of {sorted(VALUATION_METHODS)}"
            )
        metrics = _load("metrics.json")
        return CalculateValuationResponse(
            metrics=Metrics.model_validate(metrics),
            reverse_dcf=ReverseDcf.model_validate(metrics["reverse_dcf"]),
            notes=[
                f"methods: {methods}",
                f"peers: {peer_tickers or 'default'}",
                f"assumptions: {assumptions or 'default'}",
            ],
        ).model_dump(mode="json")

    return server


if __name__ == "__main__":  # stdio entry point
    build_fake_server().run(transport="stdio")
