"""Fetch and clean the primary document of a filing.

Specified by docs/data-model.md "Filing sections" and docs/adr/0006.

Produces plain text with HTML stripped and character offsets preserved, so a
FilingSection can point back into the original document. Nothing here
summarises: an agent must be able to quote a filing verbatim, and the verifier
string-matches that quote.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations


def primary_document_name(submissions: dict, accession: str) -> str:
    """Name of the main document of a filing (not an exhibit)."""
    raise NotImplementedError("TODO(roadmap Step 3, P1)")


def to_plain_text(html: bytes) -> str:
    """Strip HTML to plain text, preserving reading order and paragraph breaks.

    Offsets into the RETURNED string are what FilingSection stores, so this
    function must be deterministic: the same input always yields the same text.
    """
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
