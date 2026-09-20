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
from data.ingest import edgar_client, market_client
from data.normalize import baseline as baseline_rules
from data.normalize import factsheet as factsheet_rules
from data.normalize import peers as peer_rules
from data.normalize import scope as scope_rules
from data.normalize import snapshot as snapshot_rules
from data.normalize import to_facts
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


@lru_cache(maxsize=32)
def load_facts(ticker: Ticker, as_of: ISODate | None = None) -> CompanyData:
    """Resolve, fetch and normalize one ticker. Memoised per process."""
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


def clear_cache() -> None:
    """Drop the memoised facts. Tests call this between cases."""
    load_facts.cache_clear()


def check_scope(ticker: Ticker, as_of: ISODate | None = None) -> dict:
    """Three-level scope decision (data/normalize/scope.py)."""
    return scope_rules.check_scope(ticker, as_of).model_dump(mode="json")


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
