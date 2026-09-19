"""Split a filing's plain text into FilingSection rows.

Specified by docs/adr/0006 and docs/data-model.md "Filing sections".

Offsets are the point: every section records char_start and char_end into the
document it came from, so a quote can be located exactly and the verifier's
string match has somewhere to stand.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from schema.contracts.filings import Filing, FilingSection


def find_headings(text: str) -> list[tuple[int, str]]:
    """Return (offset, heading) for every structural heading, in document order.

    The table of contents repeats every Item heading near the top of a 10-K;
    those matches must be discarded or every section will be empty.
    """
    raise NotImplementedError("TODO(roadmap Step 3, P1)")


def split(filing: Filing, text: str) -> list[FilingSection]:
    """Split one filing into canonical sections with offsets and heading paths.

    Each section runs from its heading to the next one. Text is returned
    verbatim; nothing is summarised, reordered or truncated.
    """
    raise NotImplementedError("TODO(roadmap Step 3, P1)")


def build_section_id(accession: str, item: str) -> str:
    """Deterministic section id: sec:<accession>:<item>."""
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
