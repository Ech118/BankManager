"""Protocols that cross a partition boundary (ADR 0007).

Specified by docs/data-model.md and docs/mcp-tools.md.

  FactRepository / FilingRepository / MarketRepository
      IMPLEMENTED BY P1 (data/repositories/), CONSUMED BY P1's own mcp_server.
      Two implementations exist per protocol: a Postgres one for MODE=live and a
      fixture-backed one for MODE=mock, so mock mode needs no database at all.

  McpClient
      CONSUMED BY P3 (orchestrator/mcp_client.py). P3 reaches data ONLY through
      this. In mock mode and tests it runs over the MCP SDK's in-memory
      transport; in live mode over stdio (docs/mcp-tools.md).

These are typing.Protocol, not base classes: an implementation satisfies one by
having the right methods, so no partition has to import another's module to
inherit from it.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from schema.contracts.common import FactId, ISODate, SectionId, Ticker
from schema.contracts.facts import FinancialFact
from schema.contracts.filings import Filing, FilingSection
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer


@runtime_checkable
class FactRepository(Protocol):
    """Point-in-time access to the financial truth layer.

    EVERY method takes `as_of` and must exclude anything filed after it. An
    implementation that ignores `as_of` silently contaminates the backtest
    (error A), so tests assert the behaviour rather than trusting the signature.
    """

    def get_facts(
        self,
        ticker: Ticker,
        metrics: list[str],
        as_of: ISODate,
        *,
        period_type: str | None = None,
        periods: int | None = None,
        include_superseded: bool = False,
    ) -> list[FinancialFact]:
        """Reported and derived facts, newest first, filed on or before `as_of`.

        Restated values are excluded unless `include_superseded` is True.
        """
        ...

    def resolve_fact(self, fact_id: FactId, as_of: ISODate) -> FinancialFact | None:
        """One fact by id, or None when it does not exist or post-dates `as_of`."""
        ...

    def put_facts(self, facts: list[FinancialFact]) -> int:
        """Upsert facts, linking restatements via superseded_by. Returns rows written."""
        ...

    def latest_period(self, ticker: Ticker, as_of: ISODate, *, annual: bool = True) -> str | None:
        """Newest fiscal period label visible at `as_of`."""
        ...


@runtime_checkable
class FilingRepository(Protocol):
    """Structured access to filings and their sections. No embeddings (ADR 0006)."""

    def search_filings(
        self,
        ticker: Ticker,
        as_of: ISODate,
        *,
        forms: list[str] | None = None,
        limit: int = 20,
    ) -> list[Filing]:
        """Filings filed on or before `as_of`, newest first."""
        ...

    def get_section(self, section_id: SectionId, as_of: ISODate) -> FilingSection | None:
        """One parsed section verbatim, or None when it post-dates `as_of`."""
        ...

    def search_sections(
        self,
        ticker: Ticker,
        query: str,
        as_of: ISODate,
        *,
        forms: list[str] | None = None,
        items: list[str] | None = None,
        limit: int = 10,
    ) -> list[FilingSection]:
        """Postgres full-text search scoped by ticker, form, item and date."""
        ...

    def put_filing(self, filing: Filing, sections: list[FilingSection]) -> int:
        """Store a filing and its parsed sections. Returns sections written."""
        ...


@runtime_checkable
class MarketRepository(Protocol):
    """Market data, company identity, peers and news, all point-in-time."""

    def get_snapshot(self, ticker: Ticker, as_of: ISODate) -> MarketSnapshot | None:
        """Price, shares and the EV bridge as observed on or before `as_of`."""
        ...

    def get_profile(self, ticker: Ticker, as_of: ISODate) -> CompanyProfile | None:
        """Identity and SIC classification, which drives check_scope."""
        ...

    def get_peers(self, ticker: Ticker, as_of: ISODate, *, limit: int = 6) -> list[Peer]:
        """Comparable companies. Deterministic where possible (SIC + cap band)."""
        ...

    def search_news(
        self, ticker: Ticker, as_of: ISODate, *, lookback_days: int = 60, limit: int = 20
    ) -> list[NewsItem]:
        """Headlines published on or before `as_of`, newest first."""
        ...


@runtime_checkable
class McpClient(Protocol):
    """How P3 talks to the data layer. The ONLY route; P3 imports no data module.

    Transport is in-memory for mock mode and tests, stdio for live mode. Both
    satisfy this protocol, so agent code is identical in either mode.
    """

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke one MCP tool by name. Raises on an unknown tool or invalid arguments."""
        ...

    def list_tools(self) -> list[str]:
        """Names of the tools this server exposes. Exactly the ten in tools.py."""
        ...

    def close(self) -> None:
        """Release the transport. Safe to call more than once."""
        ...
