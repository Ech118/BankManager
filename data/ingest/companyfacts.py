"""XBRL facts from EDGAR: companyfacts and per-filing company-concept data.

Specified by docs/sec-pitfalls.md "Restatements" and docs/adr/0003.

THE TRAP THIS MODULE EXISTS TO AVOID: `companyfacts` returns the LATEST value
for every concept, which means RESTATED values. Using it for a historical run
leaks information that did not exist at the time and quietly invents a backtest
result. For any run with an `as_of`, facts must come from the filings that
existed then, keyed by their own accession numbers.

TODO(roadmap Step 1, P1): companyfacts fetch for latest-mode runs.
TODO(roadmap Step 2, P1): per-filing point-in-time fetch and restatement linking.
"""

from __future__ import annotations

from schema.contracts.common import ISODate

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
COMPANYCONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:0>10}/us-gaap/{tag}.json"


def fetch_companyfacts(cik: str) -> dict:
    """Every XBRL concept the filer has ever reported, at its LATEST value.

    Safe only for as_of=None runs. Never use this for a backtest.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def fetch_concept(cik: str, tag: str) -> dict:
    """One concept's full history, with the accession each value came from.

    Each entry carries `accn`, `filed`, `start`, `end` and `frame`, which is what
    makes point-in-time reconstruction possible.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")


def facts_as_of(cik: str, tag: str, as_of: ISODate) -> list[dict]:
    """Values for one concept AS THEY WERE KNOWN on `as_of`.

    Keeps, for each fiscal period, the value from the latest filing filed on or
    before `as_of` - not the latest filing overall.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")
