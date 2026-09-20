"""Live repositories: the Protocols in schema/contracts/interfaces.py, backed
by EDGAR and the market provider rather than by fixtures or Postgres.

Specified by docs/adr/0007. `mcp_server/backends.py` picks these when MODE=live,
and every tool above that line is unchanged - which is the point of the
Protocols existing.

WHY THIS IS NOT PostgresFactRepository
    The Postgres repositories store what has been ingested. These compute it on
    demand from `data.live`, which memoises per process. A run reads one
    company, so "fetch and normalize once, then answer from memory" is the whole
    persistence layer a run needs. Postgres earns its place when facts have to
    outlive a process - a backtest over many companies, or a warm cache shared
    between runs - and the tools above will not notice the swap.

WRITES RAISE
    Every MCP tool is read-only and there should never be one that writes
    (docs/mcp-tools.md). `put_facts` and `put_filing` exist because the Protocol
    declares them; they raise rather than silently doing nothing, so a caller
    that thinks it is persisting something finds out immediately.
"""

from __future__ import annotations

from schema.contracts.common import FactId, ISODate, SectionId, Ticker
from schema.contracts.facts import FinancialFact
from schema.contracts.filings import Filing, FilingSection
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer


def _live():
    from data import live

    return live


class LiveFactRepository:
    """Normalized XBRL facts for one company at a time."""

    def _facts(self, ticker: Ticker, as_of: ISODate | None) -> list[FinancialFact]:
        return _live().load_facts(ticker, as_of).facts

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
        wanted = set(metrics)
        out = [
            f
            for f in self._facts(ticker, as_of)
            if f.metric in wanted
            and (include_superseded or f.is_current)
            and (not as_of or not f.filed_at or f.filed_at <= as_of)
            and (period_type is None or f.period_type.value == period_type)
        ]
        out.sort(key=lambda f: (f.period_end, f.fiscal_period or ""), reverse=True)
        return out[:periods] if periods else out

    def resolve_fact(self, fact_id: FactId, as_of: ISODate) -> FinancialFact | None:
        fact = self.lookup_regardless_of_date(fact_id)
        if fact is None or (fact.filed_at and as_of and fact.filed_at > as_of):
            return None
        return fact

    def latest_period(
        self, ticker: Ticker, as_of: ISODate, *, annual: bool = True
    ) -> str | None:
        periods = [
            f.fiscal_period
            for f in self._facts(ticker, as_of)
            if f.fiscal_period and (not annual or f.fiscal_period.startswith("FY"))
        ]
        return max(periods) if periods else None

    # ------------------------------------------------------------------
    # Beyond the Protocol - what resolve_fact needs to tell three cases apart
    # ------------------------------------------------------------------
    def lookup_regardless_of_date(self, fact_id: FactId) -> FinancialFact | None:
        """The fact if it exists at all, in any company this run has loaded.

        A fact_id carries its ticker (fact:<TICKER>:<metric>:<period>), so the
        company is recoverable from the id itself rather than from whatever
        happens to be cached - which matters because the verifier resolves ids
        it was handed, possibly after the run moved on.
        """
        parts = fact_id.split(":")
        tickers = [parts[1]] if len(parts) > 2 else []
        tickers += [t for t in _live().loaded_tickers() if t not in tickers]
        for ticker in tickers:
            try:
                facts = self._facts(ticker, None)
            except Exception:  # noqa: BLE001 - an unresolvable ticker is not a fact
                continue
            for fact in facts:
                if fact.fact_id == fact_id:
                    return fact
        return None

    def is_visible_at(self, fact_id: FactId, as_of: ISODate | None) -> bool:
        fact = self.lookup_regardless_of_date(fact_id)
        if fact is None:
            return False
        return not (fact.filed_at and as_of and fact.filed_at > as_of)

    def put_facts(self, facts: list[FinancialFact]) -> int:
        raise NotImplementedError(
            "LiveFactRepository is read-only. Facts are normalized on demand from "
            "EDGAR; use PostgresFactRepository to persist them."
        )


class LiveFilingRepository:
    """Filings and the sections extracted from the latest 10-K."""

    def _sections(self, ticker: Ticker, as_of: ISODate | None) -> list[FilingSection]:
        return _live().load_sections(ticker, as_of).sections

    def search_filings(
        self,
        ticker: Ticker,
        as_of: ISODate,
        *,
        forms: list[str] | None = None,
        limit: int = 20,
    ) -> list[Filing]:
        rows = _live().search_filings(ticker, as_of, forms, limit)
        return [Filing.model_validate(row) for row in rows]

    def get_section(self, section_id: SectionId, as_of: ISODate) -> FilingSection | None:
        for ticker in _live().loaded_tickers():
            for section in self._sections(ticker, as_of):
                if section.section_id == section_id:
                    if as_of and section.filed_at > as_of:
                        return None
                    return section
        return None

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
        from data.sections import search as section_search

        sections = self._sections(ticker, as_of)
        hits = section_search.search(
            sections,
            [s.text for s in sections],
            query,
            as_of=as_of,
            forms=forms,
            items=items,
            limit=limit or len(sections),
        )
        return [hit.section for hit in hits]

    def section_exists(self, section_id: SectionId) -> bool:
        """Ignoring as_of, so the tool can tell an unknown id from a future one."""
        for ticker in _live().loaded_tickers():
            if any(s.section_id == section_id for s in self._sections(ticker, None)):
                return True
        return False

    def put_filing(self, filing: Filing, sections: list[FilingSection]) -> int:
        raise NotImplementedError(
            "LiveFilingRepository is read-only. Sections are extracted on demand; "
            "use PostgresFilingRepository to persist them."
        )


class LiveMarketRepository:
    """Price, profile, peers and news from the market provider and SEC."""

    def get_snapshot(self, ticker: Ticker, as_of: ISODate) -> MarketSnapshot | None:
        return MarketSnapshot.model_validate(_live().market_snapshot(ticker, as_of))

    def get_profile(self, ticker: Ticker, as_of: ISODate) -> CompanyProfile | None:
        return CompanyProfile.model_validate(_live().company_profile(ticker, as_of))

    def get_peers(self, ticker: Ticker, as_of: ISODate, *, limit: int = 6) -> list[Peer]:
        return [
            Peer.model_validate(row)
            for row in _live().peer_companies(ticker, as_of, limit)
        ]

    def search_news(
        self,
        ticker: Ticker,
        as_of: ISODate,
        *,
        lookback_days: int = 60,
        limit: int = 20,
    ) -> list[NewsItem]:
        return [
            NewsItem.model_validate(row)
            for row in _live().search_news(ticker, as_of, lookback_days, limit)
        ]
