"""XBRL facts from EDGAR: companyfacts and per-filing company-concept data.

Specified by docs/sec-pitfalls.md "Restatements" and docs/adr/0003.

THE TRAP THIS MODULE EXISTS TO AVOID: naive use of `companyfacts` returns the
LATEST value for every concept, which means RESTATED values. Reasoning from
those in a historical run leaks information that did not exist at the time and
quietly invents a backtest result.

WHAT THE PAYLOAD ACTUALLY CONTAINS
    Verified against AAPL, MSFT, NVDA, AMZN, GOOGL, KO, WDFC, JPM, O and TSM:
    companyfacts keeps EVERY filed version of every period, each carrying its
    own `accn` and `filed`. NVDA's year ending 2023-01-29 appears three times,
    from the FY2023, FY2024 and FY2025 10-Ks.

    So the endpoint is point-in-time capable, and the trap is narrower than
    "never use companyfacts": it bites code that takes the last entry per period
    without reading `filed`. data/normalize/restatements.py reads `filed`, which
    is why one fetch per company replaces about twenty companyconcept requests
    against an 8 req/s budget.

    `fetch_concept` stays for the case companyfacts cannot serve: a concept
    whose history was truncated, or a dimensioned disclosure.

CACHING
    A day, not forever. The payload changes whenever the filer files, and a
    point-in-time run re-derives what was visible from the `filed` dates inside
    it rather than from the age of the cache entry.
"""

from __future__ import annotations

import json

from data.ingest import cache
from schema.contracts.common import ISODate

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
COMPANYCONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:0>10}/us-gaap/{tag}.json"

COMPANYFACTS_TTL = cache.DAY_SECONDS


def fetch_companyfacts(cik: str) -> dict:
    """Every XBRL concept the filer has ever reported, all filed versions.

    Point-in-time SAFE as long as the caller filters on each entry's `filed`,
    which data/normalize/to_facts.py does. Raises httpx.HTTPStatusError for a
    CIK with no XBRL data at all.
    """
    from data.ingest import edgar_client

    padded = str(cik).zfill(10)
    raw = edgar_client.cached_fetch(
        COMPANYFACTS_URL.format(cik=padded),
        f"sec/companyfacts/{padded}.json",
        COMPANYFACTS_TTL,
    )
    return json.loads(raw)


def fetch_concept(cik: str, tag: str) -> dict:
    """One concept's full history, with the accession each value came from.

    Each entry carries `accn`, `filed`, `start`, `end` and `frame`, which is what
    makes point-in-time reconstruction possible.
    """
    from data.ingest import edgar_client

    padded = str(cik).zfill(10)
    raw = edgar_client.cached_fetch(
        COMPANYCONCEPT_URL.format(cik=padded, tag=tag),
        f"sec/companyconcept/{padded}/{tag}.json",
        COMPANYFACTS_TTL,
    )
    return json.loads(raw)


def facts_as_of(cik: str, tag: str, as_of: ISODate) -> list[dict]:
    """Values for one concept AS THEY WERE KNOWN on `as_of`.

    Keeps, for each fiscal period, the value from the latest filing filed on or
    before `as_of` - not the latest filing overall.
    """
    payload = fetch_concept(cik, tag)
    latest: dict[tuple, dict] = {}
    for unit, entries in (payload.get("units") or {}).items():
        for entry in entries:
            filed = entry.get("filed")
            if filed and filed > as_of:
                continue
            key = (unit, entry.get("start"), entry.get("end"), entry.get("form"))
            seen = latest.get(key)
            if seen is None or (entry.get("filed") or "") > (seen.get("filed") or ""):
                latest[key] = {**entry, "unit": unit}
    return sorted(latest.values(), key=lambda e: (e.get("end") or ""), reverse=True)
