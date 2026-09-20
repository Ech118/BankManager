"""Record a 10-K's extracted plain text into fixtures/real/<TICKER>/.

    MODE=live python -m data.record.sections AAPL NVDA KO JPM MSFT

WHY THE TEXT AND NOT THE HTML
    The five primary documents total 29MB of HTML; JPMorgan's alone is 12.9MB.
    Their plain-text form is 3MB, and 740KB gzipped, which is what lands here.

    That keeps the hard part under test. Everything that goes wrong in section
    extraction - the table of contents naming every Item, letter-spaced
    headings, cross-references that look like headings, knowing where Item 1A
    ends - happens in the text, and these fixtures exercise all of it end to
    end.

    What is NOT covered is the HTML-to-text conversion itself; that is tested
    against small handwritten documents in data/tests/test_sections.py, where a
    specific tag behaviour can actually be asserted rather than inferred.

GZIP, AND WHY THE TEXT IS STORED VERBATIM
    Offsets are the product here: a FilingSection's char_start and char_end
    index into exactly this string, and the verifier locates quotes with them.
    Trimming the text to save space would move every offset after the cut and
    make the fixtures test a document that does not exist.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "real"

DEFAULT_TICKERS = ("AAPL", "NVDA", "KO", "JPM", "MSFT")

AS_OF = "2026-09-19"


def text_path(ticker: str) -> Path:
    return FIXTURES_ROOT / ticker / "tenk_text.txt.gz"


def meta_path(ticker: str) -> Path:
    return FIXTURES_ROOT / ticker / "tenk.json"


def load(ticker: str) -> tuple[str, dict]:
    """The recorded 10-K text and its filing metadata. Never hits the network."""
    if not text_path(ticker).exists():
        raise FileNotFoundError(
            f"{text_path(ticker)} is missing. Record it with: "
            f"MODE=live python -m data.record.sections {ticker}"
        )
    text = gzip.decompress(text_path(ticker).read_bytes()).decode("utf-8")
    return text, json.loads(meta_path(ticker).read_text(encoding="utf-8"))


def record(ticker: str, as_of: str) -> tuple[str, dict]:
    from data.ingest import edgar_client
    from data.sections import parser

    cik = edgar_client.lookup_cik(ticker)
    filings = edgar_client.list_filings(cik, as_of, forms=["10-K"])
    if not filings:
        raise ValueError(f"{ticker}: no 10-K filed on or before {as_of}")

    filing = filings[0]
    raw = edgar_client.fetch_document(
        cik, filing["accession"], filing["primary_document"]
    )
    text = parser.to_plain_text(raw)
    meta = {
        "ticker": ticker,
        "cik": cik,
        "as_of": as_of,
        "accession": filing["accession"],
        "form": filing["form"],
        "filed_at": filing["filed_at"],
        "period_end": filing["period_end"],
        "primary_document": filing["primary_document"],
        "html_bytes": len(raw),
        "text_chars": len(text),
    }
    return text, meta


def main(argv: list[str]) -> int:
    import os

    if os.environ.get("MODE", "mock").lower() != "live":
        print("Set MODE=live: this recorder fetches documents from SEC.")
        return 2

    for ticker in [t.upper() for t in argv[1:]] or list(DEFAULT_TICKERS):
        text, meta = record(ticker, AS_OF)
        directory = FIXTURES_ROOT / ticker
        directory.mkdir(parents=True, exist_ok=True)
        text_path(ticker).write_bytes(gzip.compress(text.encode("utf-8"), 9))
        meta_path(ticker).write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(
            f"{ticker}: {meta['accession']} {meta['filed_at']}  "
            f"{meta['html_bytes'] / 1e6:.1f}MB html -> "
            f"{meta['text_chars'] / 1000:.0f}KB text -> "
            f"{text_path(ticker).stat().st_size // 1024}KB gz"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
