"""SEC EDGAR client: submissions index and filing documents.

Specified by docs/data-model.md "Ingestion" and docs/sec-pitfalls.md.

Read-only. Rate-limited through data.ingest.rate_limit and cached by accession
number. Returns raw payloads; data/normalize/ and data/sections/ interpret them.

CACHING (docs/sec-pitfalls.md 6)
    A filing document is immutable once published, so it is cached forever under
    its accession. The ticker->CIK map and a filer's submissions index both
    change as new filings arrive, so those get a one-day TTL.

TESTING
    `set_client()` swaps in an httpx client built on a MockTransport, which is
    how the tests replay recorded responses without touching the network.

TODO(roadmap Step 3, P1): full document download for section parsing.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from data.ingest import cache
from data.ingest.rate_limit import (
    EDGAR_BACKOFF_SECONDS,
    RETRY_STATUS_CODES,
    RateLimiter,
    user_agent,
)
from schema.contracts.common import ISODate, Ticker

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

TICKER_MAP_TTL = cache.DAY_SECONDS
SUBMISSIONS_TTL = cache.DAY_SECONDS

_limiter = RateLimiter()
_client: httpx.Client | None = None


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------
def set_client(client: httpx.Client | None) -> None:
    """Install an httpx client (tests) or reset to the real one (None)."""
    global _client
    _client = client


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
            follow_redirects=True,
        )
    return _client


def _fetch(url: str) -> bytes:
    """GET `url`, rate-limited, retrying politely on 429/503.

    Raises httpx.HTTPStatusError once the backoff schedule is exhausted, or
    immediately for any other 4xx/5xx - retrying a 404 just wastes the budget.
    """
    attempts = len(EDGAR_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        _limiter.acquire()
        response = _http().get(url)
        if response.status_code in RETRY_STATUS_CODES and attempt < attempts - 1:
            time.sleep(EDGAR_BACKOFF_SECONDS[attempt])
            continue
        response.raise_for_status()
        return response.content
    raise RuntimeError(f"unreachable: retry loop exhausted for {url}")


def _cached_fetch(url: str, key: str, ttl: float | None) -> bytes:
    """Fetch through the cache. `ttl=None` means the payload is immutable."""
    hit = cache.get(key) if ttl is None else cache.get_fresh(key, ttl)
    if hit is not None:
        return hit
    payload = _fetch(url)
    cache.put(key, payload)
    return payload


# --------------------------------------------------------------------------
# ticker -> CIK
# --------------------------------------------------------------------------
def normalize_ticker(ticker: str) -> str:
    """Normalise a ticker to the spelling SEC's own files use.

    Share classes are written several ways in the wild - BRK.B, BRK-B, brk/b -
    and SEC uses the hyphen. Normalising here means callers may pass whichever
    form a user typed.
    """
    return (ticker or "").strip().upper().replace(".", "-").replace("/", "-")


def fetch_ticker_map() -> dict[str, str]:
    """SEC's ticker -> zero-padded CIK map, refreshed daily.

    Keys are normalised, so both BRK.B and BRK-B resolve through
    `normalize_ticker` before lookup.
    """
    raw = _cached_fetch(COMPANY_TICKERS_URL, "sec/company_tickers.json", TICKER_MAP_TTL)
    entries: Any = json.loads(raw)

    # SEC ships this as {"0": {...}, "1": {...}}, not a list.
    rows = entries.values() if isinstance(entries, dict) else entries
    out: dict[str, str] = {}
    for row in rows:
        ticker = normalize_ticker(str(row.get("ticker", "")))
        cik = str(row.get("cik_str", "")).strip()
        if ticker and cik:
            out[ticker] = cik.zfill(10)
    return out


def lookup_cik(ticker: Ticker) -> str:
    """Resolve a ticker to a zero-padded CIK via the SEC company_tickers file.

    Raises KeyError when the ticker is not an SEC filer - which is a real
    answer, not a failure: ADRs, delisted names and typos all land here, and
    check_scope turns it into a sentence a user can read.
    """
    normalized = normalize_ticker(ticker)
    mapping = fetch_ticker_map()
    if normalized not in mapping:
        raise KeyError(
            f"{ticker!r} is not in SEC's company_tickers.json. It may be a "
            "non-US listing, an ADR, or delisted."
        )
    return mapping[normalized]


# --------------------------------------------------------------------------
# submissions
# --------------------------------------------------------------------------
def fetch_submissions(cik: str) -> dict:
    """Raw submissions index for one filer: every filing, form type and filing date.

    This is the source of `filed_at`, which every point-in-time query depends on.
    """
    padded = str(cik).zfill(10)
    raw = _cached_fetch(
        SUBMISSIONS_URL.format(cik=padded), f"sec/submissions/{padded}.json", SUBMISSIONS_TTL
    )
    return json.loads(raw)


def list_filings(
    cik: str, as_of: ISODate | None = None, forms: list[str] | None = None
) -> list[dict]:
    """Filings filed on or before `as_of`, newest first.

    Filters on the SEC's `filingDate`, never on period end: a 10-K for FY2023
    filed in 2024 must be invisible to a run with as_of in 2023 (ADR 0003).

    NOTE: reads `filings.recent` only, which holds roughly the last thousand
    filings. Long-lived filers keep older ones in `filings.files`; paging into
    those is TODO(roadmap Step 2, P1) and matters only for history deeper than
    `recent` reaches.
    """
    submissions = fetch_submissions(cik)
    recent = (submissions.get("filings") or {}).get("recent") or {}

    accessions = recent.get("accessionNumber") or []
    wanted = set(forms) if forms else None

    # SEC ships parallel arrays, one per field. Zip them into rows up front
    # rather than indexing inside the loop; a short array then pads with "".
    def column(name: str) -> list:
        values = recent.get(name) or []
        return list(values) + [""] * (len(accessions) - len(values))

    rows = zip(
        accessions,
        column("form"),
        column("filingDate"),
        column("reportDate"),
        column("primaryDocument"),
        column("isXBRL"),
        strict=False,
    )

    out: list[dict] = []
    for accession, form, filed_at, period_end, document, is_xbrl in rows:
        if as_of and filed_at and filed_at > as_of:
            continue
        if wanted is not None and form not in wanted:
            continue
        out.append(
            {
                "accession": accession,
                "form": form,
                "filed_at": filed_at,
                "period_end": period_end or None,
                "primary_document": document or None,
                "is_xbrl": is_xbrl in (1, "1", True),
            }
        )

    out.sort(key=lambda f: (f["filed_at"] or "", f["accession"]), reverse=True)
    return out


def fetch_document(cik: str, accession: str, document: str) -> bytes:
    """One filing document, cached forever (filings are immutable once published)."""
    url = ARCHIVES_URL.format(
        cik=str(cik).lstrip("0"),
        accession_nodash=accession.replace("-", ""),
        document=document,
    )
    return _cached_fetch(url, cache.accession_key(accession, document), None)
