"""Split a filing's plain text into FilingSection rows.

Specified by docs/adr/0006 and docs/data-model.md "Filing sections".

Offsets are the point: every section records char_start and char_end into the
document it came from, so a quote can be located exactly and the verifier's
string match has somewhere to stand. Nothing here summarises, reorders or
truncates - an agent must be able to quote a filing verbatim.

THE TABLE OF CONTENTS IS THE WHOLE PROBLEM
    A 10-K names every Item twice: once in the contents near the top, once where
    the section actually is. Naive heading matching takes the first hit, so every
    section becomes the one line of the contents entry that follows it - a
    parser that returns "Item 1. Business ...... 3" as Apple's business
    description, confidently and with correct offsets.

    The rule that works is: the real heading is the FIRST one with a real body
    after it. A contents entry is followed almost immediately by the next
    contents entry; a section is followed by thousands of characters of prose.

    Two rules that do NOT work, both tried against the recorded filings:

    - "Take the occurrence with the most text after it." The last candidate in a
      document always wins, because its span runs to the end of the file.
      JPMorgan's 10-K mentions "Item 1A: Risk Factors in JPMorganChase's 2025
      Form 10-K" 590KB from the end, and that cross-reference beat the real
      section at offset 279,411.
    - "Take the last occurrence." Same failure, for the same reason: filings
      cross-reference their own Items deep in the text, and JPMorgan does it
      four times.

A SECTION THAT LOOKS WRONG IS NOT RETURNED
    Better no section than a plausible wrong one. An extraction that comes out
    shorter than MIN_SECTION_CHARS, or with no heading, is dropped with a gap
    rather than handed to an agent - the failure mode this avoids is an agent
    quoting a table-of-contents line as a risk factor, which reads as data and
    is not.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field
from functools import lru_cache

from data.sections.items import SQUASHED_ITEM_PATTERNS, SQUASHED_TERMINATORS
from schema.contracts.enums import ItemCode
from schema.contracts.filings import Filing, FilingSection

MIN_SECTION_CHARS = 1500
"""Below this an "Item 1" is a contents line or a cross-reference, not a
business description. Apple's shortest real Item 1A run to tens of thousands;
the shortest genuine section in the recorded set is comfortably above this."""

# A heading needs MIN_SECTION_CHARS of text before the next heading to count as
# a real section. JPMorgan's contents block puts four Item headings within 930
# characters of each other; a smaller threshold let its "Item 1A" contents line
# through with 526 characters of siblings behind it.

_SCRIPT_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_BLOCK_TAGS = re.compile(
    r"</?(p|div|tr|table|br|h[1-6]|li|ul|ol|thead|tbody|section|article)\b[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>")
_HIDDEN = re.compile(r"<[^>]*style\s*=\s*[\"'][^\"']*display\s*:\s*none[^\"']*[\"'][^>]*>")
_SPACES = re.compile(r"[ \t\xa0  ]+")
_BLANKS = re.compile(r"\n{3,}")


def to_plain_text(raw: bytes | str) -> str:
    """Strip HTML to plain text, preserving reading order and paragraph breaks.

    Offsets into the RETURNED string are what FilingSection stores, so this must
    be deterministic: the same input always yields the same text, on every
    machine and every run. No dependence on dict ordering, locale or a parser's
    error recovery.
    """
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw

    text = _SCRIPT_STYLE.sub(" ", text)
    # Block-level tags become newlines so headings stay on their own lines;
    # everything else becomes a space so words do not run together.
    text = _BLOCK_TAGS.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html_module.unescape(text)

    # Normalise the whitespace filers use for layout. Non-breaking spaces are
    # everywhere in EDGAR HTML and would otherwise defeat every heading regex.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class Heading:
    """One candidate heading: where it is, and which canonical Item it names."""

    offset: int
    item: ItemCode
    text: str


@dataclass
class SplitResult:
    sections: list[FilingSection] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


ITEM_ORDER: dict[ItemCode, int] = {
    ItemCode.BUSINESS: 1,
    ItemCode.RISK_FACTORS: 2,
    ItemCode.MDNA: 3,
    ItemCode.FINANCIAL_STATEMENTS: 4,
    ItemCode.CONTROLS: 5,
}
"""A 10-K presents its Items in this order. Used to throw out a heading that
cannot be where it claims: Coca-Cola's exhibit index mentions Item 9A 70,000
characters BEFORE Item 1, and taking that at face value hands an agent 71KB of
the wrong document under the heading "Controls and Procedures"."""


def _compiled() -> list[tuple[ItemCode, re.Pattern[str]]]:
    out = []
    for item, patterns in SQUASHED_ITEM_PATTERNS.items():
        for pattern in patterns:
            out.append((item, re.compile(pattern)))
    return out


@lru_cache(maxsize=4)
def squash(text: str) -> tuple[str, tuple[int, ...]]:
    """A lowercase, whitespace-free copy, plus offset[i] -> index in `text`.

    Memoised because splitting one filing asks for it four times - candidate
    headings, terminators, and once more per boundary pass - and a 1.4MB
    JPMorgan 10-K costs a full Python-level character loop each time. Python
    caches a string's hash after the first use, so the lookup is cheap even for
    a megabyte key. Four entries is one document plus room for a test's
    fixtures.

    Every heading regex runs against this rather than the visible text, so
    letter-spaced headings ("B USINESS"), headings broken across lines and
    non-breaking spaces all match the same pattern. The map exists so a match
    still reports an offset into the REAL document - the offsets are what a
    verifier uses to find a quote.
    """
    out: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        if char.isspace():
            continue
        out.append(char.lower())
        index.append(position)
    return "".join(out), tuple(index)


def starts_a_line(text: str, offset: int) -> bool:
    """Whether only whitespace sits between `offset` and the start of its line.

    A real Item heading is on a line of its own. A cross-reference is inside a
    sentence: NVIDIA's 10-K says "see Item 1A. Risk Factors' for a discussion of
    these risks" 6,000 characters before the actual section, and without this
    check that sentence becomes the start of NVIDIA's risk factors - 121,000
    characters of genuine content under a heading that is off by a paragraph and
    a half, which is exactly the kind of wrong that reads as right.
    """
    line_start = text.rfind("\n", 0, offset) + 1
    return not text[line_start:offset].strip()


def in_canonical_order(headings: list[Heading]) -> list[Heading]:
    """The longest run of headings that appears in the order a 10-K uses.

    Anything else is a cross-reference or an index entry wearing a heading's
    clothes. Computed as a longest non-decreasing subsequence by Item rank, so
    one stray heading is dropped rather than everything after it.
    """
    if not headings:
        return []
    best: list[list[Heading]] = []
    for index, heading in enumerate(headings):
        rank = ITEM_ORDER.get(heading.item, 99)
        candidates = [
            best[j]
            for j in range(index)
            if ITEM_ORDER.get(headings[j].item, 99) < rank
        ]
        longest = max(candidates, key=len) if candidates else []
        best.append([*longest, heading])
    return max(best, key=len)


def find_headings(text: str) -> list[tuple[int, str]]:
    """Return (offset, heading) for every structural heading, in document order.

    The table of contents repeats every Item heading near the top of a 10-K;
    those matches are discarded here, so what comes back is the real sections.
    """
    return [(h.offset, h.text) for h in real_headings(text)]


def candidate_headings(text: str) -> list[Heading]:
    """Every match of every Item pattern, in document order, before filtering."""
    squashed, offsets = squash(text)
    found: list[Heading] = []
    for item, pattern in _compiled():
        for match in pattern.finditer(squashed):
            start = offsets[match.start()]
            stop = offsets[min(match.end(), len(offsets) - 1)]
            found.append(
                Heading(offset=start, item=item, text=text[start : stop + 1].strip())
            )
    found = [h for h in found if starts_a_line(text, h.offset)]
    found.sort(key=lambda h: h.offset)

    # One position can match two patterns (10-K and 10-Q MD&A numbering). Keep
    # the first; a duplicate would split a section against itself.
    deduped: list[Heading] = []
    for heading in found:
        if deduped and heading.offset - deduped[-1].offset < 4:
            continue
        deduped.append(heading)
    return deduped


def terminator_offsets(text: str) -> list[int]:
    """Offsets of headings that can only follow Item 1A, in document order."""
    squashed, offsets = squash(text)
    found: list[int] = []
    for pattern in SQUASHED_TERMINATORS:
        for match in re.finditer(pattern, squashed):
            found.append(offsets[match.start()])
    return sorted(found)


def real_headings(text: str, wanted: tuple[ItemCode, ...] | None = None) -> list[Heading]:
    """Candidates minus contents entries and cross-references.

    For each Item, the winner is the occurrence with the most text before the
    next candidate heading - a contents line is followed immediately by the next
    contents line, a real section by its body.
    """
    candidates = candidate_headings(text)
    if not candidates:
        return []

    # How far a heading is from the next STRUCTURAL marker of any kind - not
    # just the ones the caller asked for. Measuring against a filtered list
    # inflates the gap between two contents entries that happen to have an
    # unwanted Item between them, and promotes a contents line to a section.
    end = len(text)
    markers = sorted({h.offset for h in candidates} | set(terminator_offsets(text)))

    def span_of(offset: int) -> int:
        following = next((m for m in markers if m > offset), end)
        return following - offset

    best: dict[ItemCode, Heading] = {}
    for heading in candidates:
        if wanted and heading.item not in wanted:
            continue
        if heading.item in best:
            # Already found this Item's section; later hits are cross-references.
            continue
        if span_of(heading.offset) < MIN_SECTION_CHARS:
            # A heading with almost nothing after it is a contents entry.
            continue
        best[heading.item] = heading

    winners = sorted(best.values(), key=lambda h: h.offset)
    return in_canonical_order(winners)


def build_section_id(accession: str, item: str) -> str:
    """Deterministic section id: sec:<accession>:<item>."""
    return f"sec:{accession}:{item}"


def build_source_id(accession: str, item: str) -> str:
    """Citation key for Evidence: src:edgar_text:<accession>:<item>."""
    return f"src:edgar_text:{accession}:{item}"


def split(
    filing: Filing,
    text: str,
    *,
    wanted: tuple[ItemCode, ...] | None = None,
) -> SplitResult:
    """Split one filing into canonical sections with offsets and heading paths.

    Each section runs from its heading to the next one. Text is returned
    verbatim; nothing is summarised, reordered or truncated.
    """
    result = SplitResult()
    headings = real_headings(text, wanted=wanted)
    if not headings:
        result.gaps.append(
            f"{filing.accession}: no Item heading was found in the primary "
            "document, so no section could be extracted. The filing may use an "
            "unrecognised heading style."
        )
        return result

    terminators = terminator_offsets(text)
    for index, heading in enumerate(headings):
        start = heading.offset
        following = (
            headings[index + 1].offset if index + 1 < len(headings) else len(text)
        )
        # The next section heading normally ends this one. A terminator ends it
        # sooner when there is no next heading - which is the Item 1A case, and
        # the difference between the risk factors and the rest of the 10-K.
        after = [t for t in terminators if t > start]
        stop = min(following, after[0]) if after else following
        body = text[start:stop].strip()
        # Re-derive the end from the stripped body so char_end - char_start
        # equals char_count equals len(text), which FilingSection requires.
        leading = len(text[start:stop]) - len(text[start:stop].lstrip())
        char_start = start + leading
        char_end = char_start + len(body)

        if len(body) < MIN_SECTION_CHARS:
            result.gaps.append(
                f"{filing.accession} {heading.item.value}: extracted only "
                f"{len(body)} characters, below the {MIN_SECTION_CHARS} needed to "
                "be a real section. Dropped rather than returned - a "
                "table-of-contents line quoted as a risk factor reads as data."
            )
            continue

        result.sections.append(
            FilingSection(
                section_id=build_section_id(filing.accession, heading.item.value),
                source_id=build_source_id(filing.accession, heading.item.value),
                accession=filing.accession,
                company_id=filing.company_id,
                form=filing.form,
                fiscal_period=filing.fiscal_period,
                filed_at=filing.filed_at,
                item=heading.item,
                heading_path=[heading.text],
                char_start=char_start,
                char_end=char_end,
                char_count=len(body),
                text=body,
            )
        )

    if wanted:
        missing = [i.value for i in wanted if i not in {h.item for h in headings}]
        if missing:
            result.gaps.append(
                f"{filing.accession}: no heading matched {', '.join(missing)}. "
                "Nothing was returned for them rather than a guess."
            )
    return result
