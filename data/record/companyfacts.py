"""Record companyfacts + submissions into fixtures/real/<TICKER>/.

    python -m data.record.companyfacts AAPL MSFT NVDA AMZN JPM KO O WDFC TSM XOM

WHY THE PAYLOAD IS TRIMMED
    A raw companyfacts file is 3-8MB (JPM alone is 7.8MB), and ten of them would
    put 40MB of JSON in the repository. The recorder keeps only the concepts any
    chain in data/normalize/concept_map.py can ask for, which is ~40 of the
    hundreds a large filer reports, and drops every non-annual entry.

WHAT IS DELIBERATELY NOT TRIMMED
    Every FILED VERSION of every annual period is kept, with its `accn` and
    `filed`. Those duplicates are what the point-in-time and restatement tests
    are made of; collapsing them to one value per period would leave the tests
    passing against data that cannot exercise the bug.

    Both taxonomies are kept as-is for a foreign issuer (TSM), because the
    absence of a us-gaap node is the thing under test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from data.ingest import companyfacts as companyfacts_api
from data.ingest import edgar_client
from data.normalize import concept_map, periods

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "real"

KEEP_DEI: frozenset[str] = frozenset(
    {"EntityCommonStockSharesOutstanding", "EntityPublicFloat"}
)
"""Cover-page facts the market snapshot needs."""

SUBMISSION_FIELDS: tuple[str, ...] = (
    "cik",
    "name",
    "tickers",
    "exchanges",
    "sic",
    "sicDescription",
    "fiscalYearEnd",
    "stateOfIncorporation",
    "entityType",
    "category",
    "formerNames",
)
"""Identity fields. The 26,190-row `filings.recent` block is summarised instead."""


def trim_companyfacts(payload: dict, *, keep_all_taxonomies: bool = True) -> dict:
    """Keep only the concepts the concept map can ask for, annual entries only."""
    wanted = set(concept_map.all_concepts(concept_map.US_GAAP))
    facts_in = payload.get("facts") or {}
    facts_out: dict[str, dict] = {}

    for taxonomy, concepts in facts_in.items():
        if taxonomy == concept_map.US_GAAP:
            selected = {c: node for c, node in concepts.items() if c in wanted}
        elif taxonomy == "dei":
            selected = {c: node for c, node in concepts.items() if c in KEEP_DEI}
        elif taxonomy == concept_map.IFRS_FULL and keep_all_taxonomies:
            # A 20-F filer's whole story is that this node exists and us-gaap
            # does not. Keep a few concepts so the shape survives without the
            # bulk - and keep their entries unfiltered, since an IFRS filer's
            # annual report is a 20-F and would not survive the 10-K filter.
            selected = dict(sorted(concepts.items())[:3])
        else:
            continue

        unfiltered = taxonomy == concept_map.IFRS_FULL
        trimmed: dict[str, dict] = {}
        for concept, node in selected.items():
            units = {}
            for unit, entries in (node.get("units") or {}).items():
                if unfiltered:
                    kept = entries[:5]
                elif concept in EVENT_CONCEPTS:
                    kept = list(entries)
                else:
                    kept = [e for e in entries if _is_annual(e)]
                if kept:
                    units[unit] = kept
            if units:
                trimmed[concept] = {
                    "label": node.get("label"),
                    "description": node.get("description"),
                    "units": units,
                }
        if trimmed:
            facts_out[taxonomy] = trimmed

    return {
        "cik": payload.get("cik"),
        "entityName": payload.get("entityName"),
        "facts": facts_out,
    }


EVENT_CONCEPTS: frozenset[str] = frozenset(
    concept
    for metric in concept_map.NON_ANNUAL_METRICS
    for concept in concept_map.candidates(metric, concept_map.US_GAAP)
)
"""Concepts describing an EVENT rather than a reporting period, kept whole.

A stock-split ratio is tagged in whichever filing followed the split, in
whatever shape the filer chose. NVDA tagged its 2021 4-for-1 as an instant and
its 2024 10-for-1 as a MONTH-LONG DURATION (start 2024-05-01, end 2024-05-31).
An annual-only filter drops the second, which silently removes the very split
the discontinuity detector exists to explain.
"""


def _is_annual(entry: dict) -> bool:
    """Annual 10-K rows, plus every cover-page share count (any form)."""
    if entry.get("form") in periods.ANNUAL_FORMS and entry.get("fp") == "FY":
        start, end = entry.get("start"), entry.get("end")
        return not start or periods.is_annual_duration(start, end)
    return entry.get("start") is None and entry.get("form") in {"10-K", "10-Q", "10-K/A"}


def trim_submissions(payload: dict) -> dict:
    """Identity plus a form census. `filings.recent` is a window, not a history.

    JPM's `recent` holds 26,190 filings spanning one year and containing a
    single 10-K, so counting annual reports there would call JPM a company with
    no history. The census records what the window held; the scope check counts
    fiscal periods in companyfacts instead.
    """
    out = {field: payload.get(field) for field in SUBMISSION_FIELDS}
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = list(recent.get("form") or [])
    dates = [d for d in (recent.get("filingDate") or []) if d]
    census: dict[str, int] = {}
    for form in forms:
        census[form] = census.get(form, 0) + 1
    out["filings"] = {
        "recent": {
            key: list(recent.get(key) or [])[:40]
            for key in ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument")
        },
        "window": {
            "count": len(forms),
            "earliest": min(dates) if dates else None,
            "latest": max(dates) if dates else None,
            "form_census": dict(sorted(census.items(), key=lambda kv: -kv[1])[:20]),
        },
    }
    return out


def record(
    ticker: str,
    root: Path = FIXTURES_ROOT,
    *,
    cik: str | None = None,
    directory: str | None = None,
) -> Path:
    """Fetch and write fixtures/real/<TICKER>/{companyfacts,submissions}.json.

    `cik` and `directory` override ticker resolution, which is how the XOM
    holding company gets recorded alongside the Exxon Mobil Corp that
    data/ingest/ticker_overrides.py redirects XOM to.
    """
    cik = cik or edgar_client.lookup_cik(ticker)
    submissions = edgar_client.fetch_submissions(cik)
    try:
        facts = companyfacts_api.fetch_companyfacts(cik)
    except Exception as exc:  # a CIK with no XBRL at all is a real answer
        print(f"  {ticker}: companyfacts unavailable ({exc})")
        facts = {"cik": int(cik), "entityName": submissions.get("name"), "facts": {}}

    target = root / (directory or ticker.upper().replace(".", "-"))
    target.mkdir(parents=True, exist_ok=True)
    trimmed = trim_companyfacts(facts)
    (target / "companyfacts.json").write_text(
        json.dumps(trimmed, indent=1, sort_keys=True), encoding="utf-8"
    )
    (target / "submissions.json").write_text(
        json.dumps(trim_submissions(submissions), indent=1, sort_keys=True), encoding="utf-8"
    )
    size = (target / "companyfacts.json").stat().st_size // 1024
    concepts = sum(len(v) for v in trimmed["facts"].values())
    print(f"  {ticker}: cik={cik} {concepts} concepts, {size}KB -> {target}")
    return target


def load(ticker: str, root: Path = FIXTURES_ROOT) -> tuple[dict, dict]:
    """Read back a recorded (companyfacts, submissions) pair."""
    target = root / ticker.upper().replace(".", "-")
    return (
        json.loads((target / "companyfacts.json").read_text(encoding="utf-8")),
        json.loads((target / "submissions.json").read_text(encoding="utf-8")),
    )


EXTRA_FIXTURES: dict[str, tuple[str, str]] = {
    "XOM-HOLDCO": ("XOM", "0002115436"),
}
"""directory -> (ticker, cik) for a payload no ticker resolves to any more.
XOM's holding company is recorded so the "no annual history" branch of
check_scope has real data to run against."""


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for name in argv:
        extra = EXTRA_FIXTURES.get(name.upper())
        if extra:
            ticker, cik = extra
            record(ticker, cik=cik, directory=name.upper())
        else:
            record(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
