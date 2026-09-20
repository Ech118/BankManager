"""The live data layer: fetch, normalize, assemble. Private to data/.

Specified by docs/adr/0007 - nothing outside data/ imports this module.
`data/api.py` dispatches here when MODE=live and stays the public interface.

CACHING ONE TICKER'S FACTS PER PROCESS
    Every entry point needs the same normalized facts, and normalizing is pure
    CPU over a payload the EDGAR cache already holds. `load_facts` memoises by
    (ticker, as_of) so a factsheet build does the work once rather than once per
    field.

NOTHING HERE RAISES FOR MISSING DATA
    An out-of-scope ticker raises ValueError (docs/mcp-tools.md). Everything
    else - a provider outage, an unmapped concept, a share count that fails its
    sanity check - becomes an `unavailable` value plus a data_quality gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from data.ingest import companyfacts as companyfacts_api
from data.ingest import edgar_client, market_client, news_client
from data.normalize import baseline as baseline_rules
from data.normalize import factsheet as factsheet_rules
from data.normalize import peers as peer_rules
from data.normalize import scope as scope_rules
from data.normalize import snapshot as snapshot_rules
from data.normalize import to_facts
from data.sections import extract as section_extract
from schema.contracts.common import ISODate, Ticker
from schema.contracts.enums import Mode

DEFAULT_YEARS = 5


@dataclass
class CompanyData:
    """Everything one ticker's filings yielded, normalized once."""

    ticker: str
    cik: str
    submissions: dict
    companyfacts: dict
    normalized: to_facts.NormalizedFacts
    gaps: list[str] = field(default_factory=list)

    @property
    def facts(self):
        return self.normalized.facts

    @property
    def company_name(self) -> str:
        return (
            self.submissions.get("name")
            or self.companyfacts.get("entityName")
            or self.ticker
        )


_LOADED: list[Ticker] = []
"""Every ticker load_facts has served, newest last, so a section_id can be
resolved back to the company that produced it."""


@lru_cache(maxsize=32)
def load_facts(ticker: Ticker, as_of: ISODate | None = None) -> CompanyData:
    """Resolve, fetch and normalize one ticker. Memoised per process."""
    if ticker not in _LOADED:
        _LOADED.append(ticker)
    cik = edgar_client.lookup_cik(ticker)
    submissions = edgar_client.fetch_submissions(cik)
    try:
        facts_payload = companyfacts_api.fetch_companyfacts(cik)
    except Exception as exc:
        facts_payload = {"cik": int(cik), "entityName": submissions.get("name"), "facts": {}}
        normalized = to_facts.NormalizedFacts(
            ticker=ticker, gaps=[f"{ticker}: XBRL facts are unavailable from SEC ({exc})."]
        )
        return CompanyData(ticker, cik, submissions, facts_payload, normalized, normalized.gaps)

    normalized = to_facts.normalize_companyfacts(
        ticker, facts_payload, as_of=as_of, years=DEFAULT_YEARS, cik=cik
    )
    return CompanyData(ticker, cik, submissions, facts_payload, normalized, normalized.gaps)


def loaded_tickers() -> list[Ticker]:
    """Tickers this process has already normalized.

    A section_id carries an accession and an item but no ticker, so resolving
    one means asking the companies already in play. That is the right set: the
    MCP layer only ever hands back a section_id it produced, for a ticker the
    same run asked about.
    """
    return list(reversed(_LOADED))


def clear_cache() -> None:
    """Drop the memoised facts. Tests call this between cases."""
    load_facts.cache_clear()
    load_sections.cache_clear()
    _LOADED.clear()


def check_scope(ticker: Ticker, as_of: ISODate | None = None) -> dict:
    """Three-level scope decision (data/normalize/scope.py)."""
    return scope_rules.check_scope(ticker, as_of).model_dump(mode="json")


@lru_cache(maxsize=16)
def load_sections(ticker: Ticker, as_of: ISODate | None = None):
    """Item 1 and Item 1A of the latest 10-K, extracted once per process.

    Memoised for the same reason facts are: a factsheet build, a section fetch
    and a search all want the same document, and parsing a 1.4MB text three
    times to get the same answer is waste, not safety.
    """
    data = load_facts(ticker, as_of)
    latest = next((f for f in data.facts if f.fiscal_period), None)
    return section_extract.extract(
        ticker,
        data.cik,
        as_of=as_of,
        fiscal_period=latest.fiscal_period if latest else "FY0000",
        retrieved_at=to_facts.utc_now(),
    )


def search_filings(
    ticker: Ticker, as_of: ISODate | None = None, forms=None, limit: int = 20
) -> list[dict]:
    """Filings filed on or before `as_of`, newest first."""
    data = load_facts(ticker, as_of)
    rows = edgar_client.list_filings(data.cik, as_of, forms=list(forms) if forms else None)
    retrieved_at = to_facts.utc_now()
    out = []
    for row in rows[:limit]:
        out.append(
            {
                "accession": row["accession"],
                "company_id": ticker,
                "cik": data.cik,
                "form": row["form"],
                "fiscal_period": row["period_end"][:4] if row["period_end"] else "",
                "period_end": row["period_end"] or row["filed_at"],
                "filed_at": row["filed_at"],
                "retrieved_at": retrieved_at,
                "source_url": section_extract.filing_url(
                    data.cik, row["accession"], row["primary_document"] or ""
                ),
            }
        )
    return out


def get_filing_section(section_id: str, as_of: ISODate | None = None) -> dict:
    """One extracted section by id. The ticker is recovered from the id's owner."""
    raise KeyError(
        f"{section_id}: live section lookup needs the ticker; call "
        "search_filing or get_factsheet, which carry it."
    )


def search_filing(
    ticker: Ticker,
    query: str,
    as_of: ISODate | None = None,
    forms=None,
    items=None,
    limit: int = 10,
) -> list[dict]:
    """Ranked keyword search over the extracted sections."""
    from data.sections import search as section_search

    result = load_sections(ticker, as_of)
    hits = section_search.search(
        result.sections,
        [s.text for s in result.sections],
        query,
        as_of=as_of,
        forms=[str(f) for f in forms] if forms else None,
        items=[str(i) for i in items] if items else None,
        limit=limit,
    )
    return [hit.section.model_dump(mode="json") for hit in hits]


def search_news(
    ticker: Ticker, as_of: ISODate | None = None, lookback_days: int = 60, limit: int = 20
) -> list[dict]:
    """Headlines in [as_of - lookback_days, as_of], newest first."""
    effective = as_of or to_facts.utc_now()[:10]
    result = news_client.search(ticker, effective, lookback_days, limit)
    return [item.model_dump(mode="json") for item in result.news]


def build_factsheet(ticker: Ticker, as_of: ISODate | None = None) -> dict:
    """The whole reported picture of one company at one date.

    Every part is assembled from the SAME normalized facts and the SAME market
    observation, so the factsheet an auditor checks is the one the tools answer
    from. `mode` is `backtest` whenever `as_of` predates today - a run that
    reconstructs the past is not a live run, and the report says so.
    """
    from data.normalize import scope as scope_rules

    data = load_facts(ticker, as_of)
    retrieved_at = to_facts.utc_now()
    effective_as_of = as_of or retrieved_at[:10]

    scope = scope_rules.check_scope(ticker, as_of)
    gaps = list(data.gaps) + list(getattr(scope, "gaps", []) or [])

    client = market_client.get_client()
    snapshot = snapshot_rules.build(
        ticker,
        as_of=as_of,
        quote=client.quote(ticker),
        profile=client.profile(ticker),
        companyfacts=data.companyfacts,
        facts=data.facts,
        retrieved_at=retrieved_at,
    )
    gaps.extend(snapshot.gaps)

    baseline = baseline_rules.build(
        as_of=effective_as_of,
        quote=client.quote(baseline_rules.SPY),
        retrieved_at=retrieved_at,
    )
    gaps.extend(baseline.gaps)

    news = news_client.search(ticker, effective_as_of)
    gaps.extend(news.gaps)

    sections = load_sections(ticker, as_of)
    gaps.extend(sections.gaps)

    peer_result = peer_rules.select(
        ticker,
        as_of=as_of,
        sic=str(data.submissions.get("sic") or "") or None,
        target_cik=data.cik,
        target_revenue=_latest_annual_revenue(data),
        limit=peer_rules.DEFAULT_LIMIT,
    )
    gaps.extend(peer_result.gaps)

    result = factsheet_rules.build(
        ticker,
        as_of=effective_as_of,
        company_name=data.company_name,
        cik=data.cik,
        facts=data.facts,
        scope=scope,
        market=snapshot.snapshot,
        peers=peer_result.peers,
        baseline=baseline,
        retrieved_at=retrieved_at,
        gaps=gaps,
        news=news,
        sections=sections,
        mode=Mode.BACKTEST if as_of and as_of < retrieved_at[:10] else Mode.LIVE,
    )
    return result.factsheet.model_dump(mode="json")


def _latest_annual_revenue(data: CompanyData) -> float | None:
    """The target's own newest reported revenue, for ranking peers by size."""
    revenues = [
        f
        for f in data.facts
        if f.metric == "revenue" and f.is_current and f.value is not None
    ]
    if not revenues:
        return None
    return float(max(revenues, key=lambda f: f.period_end).value or 0.0) or None


def company_profile(ticker: Ticker, as_of: ISODate | None = None) -> dict:
    """Identity and SIC classification, from the filer's own SEC submissions.

    SEC is authoritative here rather than the market provider: `sic` decides
    scope and drives peer selection, and a vendor's industry label is neither
    the SEC's code nor stable.
    """
    data = load_facts(ticker, as_of)
    submissions = data.submissions
    retrieved_at = to_facts.utc_now()
    fiscal_year_end = submissions.get("fiscalYearEnd") or ""
    return {
        "ticker": ticker,
        "company_name": data.company_name,
        "cik": data.cik,
        "sic": str(submissions.get("sic") or "") or None,
        "sic_description": submissions.get("sicDescription") or None,
        "exchange": (submissions.get("exchanges") or [None])[0],
        # SEC writes MMDD; the contract wants MM-DD.
        "fiscal_year_end": (
            f"{fiscal_year_end[:2]}-{fiscal_year_end[2:]}"
            if len(fiscal_year_end) == 4
            else None
        ),
        "as_of": as_of or retrieved_at[:10],
        "retrieved_at": retrieved_at,
        "source_id": f"src:edgar_submissions:{data.cik}",
    }


def peer_companies(ticker: Ticker, as_of: ISODate | None = None, limit: int = 6) -> list[dict]:
    """Comparables by SIC and size (data/normalize/peers.py)."""
    data = load_facts(ticker, as_of)
    result = peer_rules.select(
        ticker,
        as_of=as_of,
        sic=str(data.submissions.get("sic") or "") or None,
        target_cik=data.cik,
        target_revenue=_latest_annual_revenue(data),
        limit=limit,
    )
    return [peer.model_dump(mode="json") for peer in result.peers]


def market_snapshot(ticker: Ticker, as_of: ISODate | None = None) -> dict:
    """Price, shares and the EV bridge, all stamped with one instant."""
    data = load_facts(ticker, as_of)
    client = market_client.get_client()
    result = snapshot_rules.build(
        ticker,
        as_of=as_of,
        quote=client.quote(ticker),
        profile=client.profile(ticker),
        companyfacts=data.companyfacts,
        facts=data.facts,
        retrieved_at=to_facts.utc_now(),
    )
    return result.snapshot.model_dump(mode="json")
