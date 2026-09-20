"""Fetch a filing's primary document and extract its sections.

Specified by docs/data-model.md "Filing sections".

This is the seam between the network (data/ingest) and the parsing
(data/sections/parser.py): it decides WHICH filing to read, fetches it, and
hands the text to the splitter. The parser itself never touches the network, so
it can be tested against recorded documents.

ITEM 1 AND ITEM 1A ONLY, FOR NOW
    Those are what the Business Agent reads. Restricting the request also makes
    the extraction more accurate, not less: the heading chooser has fewer
    chances to let a bogus Item displace a real one. Adding Item 7 later is a
    change to WANTED_ITEMS and nothing else.

THE LATEST 10-K ON OR BEFORE as_of
    Not the latest 10-K. A run dated June 2025 must read the 10-K that existed
    in June 2025, and `list_filings` already filters on SEC's filingDate
    (ADR 0003).

A FAILURE HERE IS A GAP, NOT AN EXCEPTION
    A filing that cannot be fetched, or whose sections do not survive the
    parser's sanity checks, produces no sections and a data_quality gap. The
    report then says the qualitative sections are missing, which is true and
    visible, rather than a run aborting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schema.contracts.common import ISODate, ISOTimestamp, Ticker
from schema.contracts.enums import ItemCode
from schema.contracts.filings import Filing, FilingSection

WANTED_ITEMS: tuple[ItemCode, ...] = (ItemCode.BUSINESS, ItemCode.RISK_FACTORS)


@dataclass
class ExtractResult:
    filing: Filing | None = None
    sections: list[FilingSection] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)


def filing_url(cik: str, accession: str, document: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/{document}"


def latest_10k(
    ticker: Ticker,
    cik: str,
    *,
    as_of: ISODate | None,
    fiscal_period: str,
    retrieved_at: ISOTimestamp,
) -> tuple[Filing | None, list[str]]:
    """The newest 10-K filed on or before `as_of`, as a contract Filing."""
    from data.ingest import edgar_client

    try:
        filings = edgar_client.list_filings(cik, as_of, forms=["10-K"])
    except Exception as exc:  # noqa: BLE001 - a fetch failure is a gap
        return None, [f"{ticker}: could not list filings from SEC ({exc})."]

    if not filings:
        return None, [
            f"{ticker}: no 10-K was filed on or before {as_of}, so Item 1 and "
            "Item 1A are unavailable."
        ]

    row = filings[0]
    if not row.get("primary_document"):
        return None, [
            f"{ticker}: the 10-K {row['accession']} names no primary document, "
            "so its sections cannot be fetched."
        ]

    filing = Filing(
        accession=row["accession"],
        company_id=ticker,
        cik=cik,
        form="10-K",
        fiscal_period=fiscal_period,
        period_end=row["period_end"] or row["filed_at"],
        filed_at=row["filed_at"],
        retrieved_at=retrieved_at,
        source_url=filing_url(cik, row["accession"], row["primary_document"]),
    )
    return filing, []


def extract(
    ticker: Ticker,
    cik: str,
    *,
    as_of: ISODate | None,
    fiscal_period: str,
    retrieved_at: ISOTimestamp,
    wanted: tuple[ItemCode, ...] = WANTED_ITEMS,
) -> ExtractResult:
    """Item 1 and Item 1A of the latest 10-K on or before `as_of`."""
    from data.ingest import edgar_client
    from data.sections import parser

    filing, gaps = latest_10k(
        ticker, cik, as_of=as_of, fiscal_period=fiscal_period, retrieved_at=retrieved_at
    )
    if filing is None:
        return ExtractResult(gaps=gaps)

    document = filing.source_url.rsplit("/", 1)[-1]
    try:
        raw = edgar_client.fetch_document(cik, filing.accession, document)
    except Exception as exc:  # noqa: BLE001 - a fetch failure is a gap
        return ExtractResult(
            filing=filing,
            gaps=[
                f"{ticker}: the 10-K {filing.accession} could not be fetched "
                f"({exc}), so Item 1 and Item 1A are unavailable."
            ],
        )

    text = parser.to_plain_text(raw)
    split = parser.split(filing, text, wanted=wanted)

    filing = filing.model_copy(
        update={"section_ids": [s.section_id for s in split.sections]}
    )
    return ExtractResult(
        filing=filing,
        sections=split.sections,
        texts={s.section_id: s.text for s in split.sections},
        gaps=[*gaps, *split.gaps],
    )
