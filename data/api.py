"""P1 (Data & MCP) owns this file. Public interface of the data layer.

Step 0 STUB: every function returns the fictional ACME fixtures from
fixtures/mock/. The owner replaces the internals (keep MODE=mock working) but
MUST NOT change any signature; that is a CONTRACT-CHANGE PR (CONTRIBUTING.md).
tests/contracts/test_signatures.py enforces the signatures.

Boundary (docs/adr/0007): other partitions never import a private module of
data/. mcp_server/ wraps these functions; P3 reaches them only through MCP.

POINT-IN-TIME (ADR 0003): every read takes `as_of`. None means "latest known".
The MCP layer always passes one explicitly, so an agent can never accidentally
see a filing from after the run's cutoff.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"
_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
_MOCK_OUT_OF_SCOPE = {
    "BANKX": "Mock: financial institution (SIC 6022). Banks are out of scope for v1."
}


class NoReportableHistory(ValueError):
    """In scope, but nothing had been filed by `as_of`.

    A subclass of ValueError so every existing caller that catches ValueError
    still works (docs/mcp-tools.md: an out-of-scope ticker is a ValueError).
    It exists so `get_factsheet` can return a null factsheet for this case
    WITHOUT swallowing genuine failures - catching bare ValueError there would
    turn a validation bug into "this company has no data", which is the kind of
    error that gets believed.
    """


def _mode() -> str:
    return os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()


def _load(name: str) -> Any:
    return json.loads((_MOCK / name).read_text(encoding="utf-8"))


def _require_mock(fn: str) -> None:
    if _mode() != "live":
        return
    raise NotImplementedError(
        f"data.api.{fn}: live mode is not implemented yet (P1, roadmap Step 1). Use MODE=mock."
    )


def _item_of(identifier: str) -> str:
    """Last path segment of a section_id or source_id, which names the item."""
    return identifier.rsplit(":", 1)[-1]


def check_scope(ticker: str, as_of: str | None = None) -> dict:
    """Return {"in_scope": bool, "reason": str|None}.

    Rejects financials, REITs and pre-revenue companies (docs/sec-pitfalls.md,
    error H). Must be called before build_factsheet.

    LIVE: three outcomes, not two. `level` rides in the extra fields as
    supported | partial | unsupported, and a bank, an insurer, a REIT or a
    foreign private issuer is `partial` - in scope, with the reason attached as
    a data_quality gap - rather than refused outright. Only `unsupported` sets
    in_scope False. See data/normalize/scope.py.
    """
    if not _TICKER_RE.match(ticker or ""):
        return {"in_scope": False, "reason": f"Invalid ticker format: {ticker!r}"}
    if _mode() == "live":
        from data.normalize import scope as scope_rules

        return scope_rules.check_scope(ticker, as_of).model_dump(mode="json")
    if ticker in _MOCK_OUT_OF_SCOPE:
        return {"in_scope": False, "reason": _MOCK_OUT_OF_SCOPE[ticker]}
    if ticker != "ACME":
        return {
            "in_scope": False,
            "reason": "Mock mode only knows the fictional ticker ACME "
            "(and BANKX for the out-of-scope path).",
        }
    return {"in_scope": True, "reason": None}


def build_factsheet(ticker: str, as_of: str | None = None) -> dict:
    """Return a Factsheet (schema/factsheet.json).

    as_of=None -> latest data. as_of="YYYY-MM-DD" -> POINT-IN-TIME: only filings
    FILED on or before that date, as originally filed (never restated); market
    data as of that date (error A). Raises ValueError if out of scope.

    MOCK: filters financial periods and sections by filed date and sets
    mode="backtest". Real P1 code must also swap restated facts for as-filed ones.
    """
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("build_factsheet")
    fs = _load("factsheet.json")
    if as_of:
        fs = copy.deepcopy(fs)
        fs["financials"] = [p for p in fs["financials"] if p["filed_date"] <= as_of]
        if not fs["financials"]:
            raise NoReportableHistory(f"No filings on or before {as_of}")
        fs["filing_sections"] = [s for s in fs["filing_sections"] if s["filed_at"] <= as_of]
        fs["news"] = [n for n in fs["news"] if n["date"] <= as_of]
        fs["as_of"] = as_of
        fs["mode"] = "backtest"
    return fs


def search_filings(
    ticker: str, as_of: str | None = None, forms: list[str] | None = None, limit: int = 20
) -> list[dict]:
    """Filings filed on or before `as_of`, newest first (MCP tool: search_filings)."""
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("search_filings")
    out = [f for f in _load("filings.json") if not as_of or f["filed_at"] <= as_of]
    if forms:
        out = [f for f in out if f["form"] in forms]
    return out[:limit]


def get_filing_section(section_id: str, as_of: str | None = None) -> dict:
    """One parsed section, text included (MCP tool: get_filing_section).

    Text is returned verbatim and is DATA, never instructions (error F).
    Raises KeyError for an unknown id.
    """
    _require_mock("get_filing_section")
    for section in _load("factsheet.json")["filing_sections"]:
        if section["section_id"] == section_id:
            if as_of and section["filed_at"] > as_of:
                raise KeyError(f"{section_id} was filed after as_of {as_of}")
            out = dict(section)
            out["text"] = get_section_text(section["source_id"])
            return out
    raise KeyError(section_id)


def get_section_text(source_id: str, as_of: str | None = None) -> str:
    """Plain text of a filing section by its CITATION id (src:edgar:...).

    Passed into audit.run_audit as `get_text` by the orchestrator, so audit/
    never imports data/. Raises KeyError if unknown.
    """
    _require_mock("get_section_text")
    path = _MOCK / "sections" / f"{_item_of(source_id)}.txt"
    if not source_id.startswith("src:edgar:") or not path.exists():
        raise KeyError(source_id)
    return path.read_text(encoding="utf-8")


def search_filing(
    ticker: str,
    query: str,
    as_of: str | None = None,
    forms: list[str] | None = None,
    items: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Ranked keyword search scoped by ticker/form/item/date (MCP tool: search_filing).

    Whole sections, never fragments; no embeddings, no chunking (ADR 0006). The
    index is in process rather than in Postgres - a run reads one company's
    filings, and ranking a few hundred sections locally beats a round trip. See
    data/sections/search.py for why, and for what ADR 0006 still forbids.

    Ranking is shared with live mode, so a relevance bug shows up offline.
    """
    from data.sections import search as section_search
    from schema.contracts.filings import FilingSection

    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("search_filing")

    sections, texts = [], []
    for raw in _load("factsheet.json")["filing_sections"]:
        text = get_section_text(raw["source_id"])
        sections.append(FilingSection.model_validate({**raw, "text": text}))
        texts.append(text)

    hits = section_search.search(
        sections, texts, query, as_of=as_of, forms=forms, items=items, limit=limit
    )
    return [hit.section.model_dump(mode="json") for hit in hits]


def get_financial_facts(
    ticker: str,
    metrics: list[str],
    as_of: str | None = None,
    period_type: str | None = None,
    periods: int | None = None,
    include_superseded: bool = False,
) -> list[dict]:
    """Reported and derived facts, newest first (MCP tool: get_financial_facts).

    Restated values are excluded unless `include_superseded` is True, so an agent
    cannot cite a number a later filing corrected (IssueType.SUPERSEDED_FACT).
    """
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("get_financial_facts")
    out = []
    for fact in _load("facts.json"):
        if fact["metric"] not in metrics:
            continue
        if not include_superseded and fact["superseded_by"]:
            continue
        if as_of and fact["filed_at"] and fact["filed_at"] > as_of:
            continue
        if period_type and fact["period_type"] != period_type:
            continue
        out.append(fact)
    out.sort(key=lambda f: f["period_end"], reverse=True)
    return out[:periods] if periods else out


def get_market_snapshot(ticker: str, as_of: str | None = None) -> dict:
    """Price, shares and the EV bridge at one instant (MCP tool: get_market_snapshot).

    LIVE: price from the market provider, shares from the filing (with a
    public-float sanity check, because a cover-page count can be one share class
    of several), cash and debt from the normalized facts. A provider outage
    yields a snapshot with price unavailable - never an exception.
    """
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    if _mode() == "live":
        from data import live

        return live.market_snapshot(ticker, as_of)
    _require_mock("get_market_snapshot")
    return _load("market_snapshot.json")


def get_company_profile(ticker: str, as_of: str | None = None) -> dict:
    """Identity and SIC classification (MCP tool: get_company_profile)."""
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("get_company_profile")
    return _load("company_profile.json")


def get_peer_companies(ticker: str, as_of: str | None = None, limit: int = 6) -> list[dict]:
    """Comparable companies (MCP tool: get_peer_companies). Deterministic where possible."""
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("get_peer_companies")
    return _load("peers.json")[:limit]


def search_news(
    ticker: str, as_of: str | None = None, lookback_days: int = 60, limit: int = 20
) -> list[dict]:
    """Recent headlines (MCP tool: search_news). Results are UNTRUSTED text (error F)."""
    scope = check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(scope["reason"])
    _require_mock("search_news")
    out = [n for n in _load("factsheet.json")["news"] if not as_of or n["date"] <= as_of]
    return out[:limit]


def resolve_fact(fact_id: str, as_of: str | None = None) -> dict:
    """One fact by id (MCP tool: resolve_fact). Used by the verifier and by agents.

    Returns the fact even when superseded or after `as_of`; the caller inspects
    `superseded_by` and `filed_at` so the verifier can raise the right issue type.
    Raises KeyError if the id does not exist.
    """
    _require_mock("resolve_fact")
    for fact in _load("facts.json"):
        if fact["fact_id"] == fact_id:
            return fact
    raise KeyError(fact_id)
