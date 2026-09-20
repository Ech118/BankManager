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
import xml.etree.ElementTree as ET
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
BROWSE_EDGAR_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json"

TICKER_MAP_TTL = cache.DAY_SECONDS
SUBMISSIONS_TTL = cache.DAY_SECONDS
SIC_LIST_TTL = cache.DAY_SECONDS
FRAMES_TTL = cache.DAY_SECONDS
"""A frame for a closed fiscal year barely moves, and the SIC roster moves
only when a company registers or re-classifies. A day is generous either way,
and it keeps a demo from re-fetching a megabyte per run."""

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


def cached_fetch(url: str, key: str, ttl: float | None) -> bytes:
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
    raw = cached_fetch(COMPANY_TICKERS_URL, "sec/company_tickers.json", TICKER_MAP_TTL)
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

    An override in data/ingest/ticker_overrides.py wins, because SEC's map
    points at the CURRENT registrant: after a holding-company reorganisation
    the ticker moves to a CIK with no filing history while every 10-K stays
    under the predecessor.

    Raises KeyError when the ticker is not an SEC filer - which is a real
    answer, not a failure: ADRs, delisted names and typos all land here, and
    check_scope turns it into a sentence a user can read.
    """
    from data.ingest.ticker_overrides import override_for

    override = override_for(ticker)
    if override is not None:
        return override.cik.zfill(10)

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
    raw = cached_fetch(
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


def _sic_page(sic: str, count: int, start: int) -> list[str]:
    """One browse-edgar page of CIKs for a SIC code.

    THE CIKs COME FROM THE ATOM MARKUP, NOT FROM THE TITLES
        The feed's <title> is "COMPANY NAME (CIK 0000320193) (Filer)" for some
        rows and a bare company name for others, and a title-parsing approach
        silently drops whichever rows it cannot match. The <CIK> element is
        present on every row, so that is what is read.
    """
    params = {
        "action": "getcompany",
        "SIC": str(sic).strip(),
        "type": "10-K",
        "dateb": "",
        "owner": "include",
        "count": str(count),
        "start": str(start),
        "output": "atom",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BROWSE_EDGAR_URL}?{query}"
    try:
        raw = cached_fetch(url, f"sec/sic/{sic}-{count}-{start}.xml", SIC_LIST_TTL)
        root = ET.fromstring(raw)
    except Exception:
        return []

    # Namespaced XML, and the namespace has changed before. Matching on the
    # local tag name survives that; a hard-coded namespace would not.
    out: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].upper() != "CIK":
            continue
        cik = (element.text or "").strip()
        if cik.isdigit():
            out.append(cik.zfill(10))
    return out


def fetch_sic_companies(sic: str, count: int = 100, pages: int = 1) -> list[str]:
    """Zero-padded CIKs of companies filing 10-Ks under `sic`, deduplicated.

    PAGING IS NOT OPTIONAL FOR A CROWDED SIC
        browse-edgar caps a page at 100 rows and orders them by neither size nor
        relevance. SIC 6021 holds hundreds of banks, mostly small: Bank of
        America is on page 1, Citigroup on page 2 and Wells Fargo on neither. A
        single page therefore misses the very companies a peer set is for.

    ONLY EXACT SIC CODES WORK
        browse-edgar returns ZERO rows for a two- or three-digit SIC prefix -
        `SIC=35` is not a wildcard, it is an unknown code. Anything that widens
        an industry search has to do it some other way; see
        data/normalize/peers.py.

    Returns [] on any failure. Peer selection is the weakest data in the system
    and must degrade to "no peers", never to an exception.
    """
    seen: list[str] = []
    known: set[str] = set()
    for page in range(max(1, pages)):
        rows = _sic_page(sic, count, page * count)
        if not rows:
            break
        for cik in rows:
            if cik not in known:
                known.add(cik)
                seen.append(cik)
        if len(rows) < count:
            break
    return seen


def fetch_frame(
    concept: str,
    period: str,
    *,
    taxonomy: str = "us-gaap",
    unit: str = "USD",
) -> dict[str, float]:
    """One XBRL frame as {zero-padded CIK: value}.

    A frame is every filer's value for one concept in one period, in ONE
    request - which is why peer ranking does not cost a request per candidate.

    THE FRAME IS CALENDAR-ALIGNED, THE FILER'S YEAR MAY NOT BE
        SEC assigns a fact to CY2024 only when its period is close enough to the
        calendar year. A January or August year end can therefore be missing
        from the frame entirely. That is a gap, not a zero: a caller that treats
        a missing CIK as "no revenue" ranks NVDA as the smallest company in its
        industry. Missing CIKs are simply absent from the returned mapping.

    Returns {} on any failure, including the 404 SEC serves for a frame that
    does not exist.
    """
    url = FRAMES_URL.format(taxonomy=taxonomy, concept=concept, unit=unit, period=period)
    key = f"sec/frames/{taxonomy}-{concept}-{unit}-{period}.json"
    try:
        raw = cached_fetch(url, key, FRAMES_TTL)
        payload = json.loads(raw)
    except Exception:
        return {}

    out: dict[str, float] = {}
    for entry in payload.get("data", []):
        cik = str(entry.get("cik", "")).strip()
        value = entry.get("val")
        if not cik.isdigit() or value is None:
            continue
        try:
            out[cik.zfill(10)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def fetch_document(cik: str, accession: str, document: str) -> bytes:
    """One filing document, cached forever (filings are immutable once published)."""
    url = ARCHIVES_URL.format(
        cik=str(cik).lstrip("0"),
        accession_nodash=accession.replace("-", ""),
        document=document,
    )
    return cached_fetch(url, cache.accession_key(accession, document), None)
