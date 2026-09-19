"""SEC EDGAR client: submissions index and filing documents.

Specified by docs/data-model.md "Ingestion" and docs/sec-pitfalls.md.

Read-only. Rate-limited through data.ingest.rate_limit and cached by accession
number. Returns raw payloads; data/normalize/ and data/sections/ interpret them.

TODO(roadmap Step 1, P1): submissions + document fetch.
TODO(roadmap Step 3, P1): full document download for section parsing.
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"


def lookup_cik(ticker: Ticker) -> str:
    """Resolve a ticker to a zero-padded CIK via the SEC company_tickers file."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def fetch_submissions(cik: str) -> dict:
    """Raw submissions index for one filer: every filing, form type and filing date.

    This is the source of `filed_at`, which every point-in-time query depends on.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def list_filings(
    cik: str, as_of: ISODate | None = None, forms: list[str] | None = None
) -> list[dict]:
    """Filings filed on or before `as_of`, newest first.

    Filters on the SEC's `filingDate`, never on period end: a 10-K for FY2023
    filed in 2024 must be invisible to a run with as_of in 2023 (ADR 0003).
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def fetch_document(cik: str, accession: str, document: str) -> bytes:
    """One filing document, cached forever (filings are immutable once published)."""
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
