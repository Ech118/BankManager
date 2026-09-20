"""Keyword search over whole filing sections. No Postgres, no embeddings.

Specified by docs/mcp-tools.md#search_filing and
docs/adr/0006-no-naive-chunk-and-embed-rag.md.

WHAT ADR 0006 ACTUALLY RULES OUT, AND WHAT IT DOES NOT
    The ADR forbids chunking filings into embeddings and retrieving fragments.
    That is untouched here: the unit of retrieval is a whole structural section,
    scoped by ticker, form, item and date, and the ranking is arithmetic a
    reviewer can reproduce by hand.

    The ADR also says search "starts as Postgres full-text search". This ranks
    in process instead. A run reads ONE company's filings - a few hundred
    sections, a few megabytes - and a process-local index over that is faster
    than a round trip, needs no service running, and keeps the offline test
    suite genuinely offline. Postgres earns its place when the corpus outgrows
    one company per run; `search()`'s signature does not change when it does.
    Recorded in docs/requests/2026-09-20-p1-to-all-get-factsheet-tool.md.

WHY BM25 AND NOT SUBSTRING MATCHING
    Substring matching answers "does this word appear", which for a 10-K is
    "yes" for almost any word and almost any section - Item 1A alone is tens of
    thousands of words. The agent then gets the longest sections rather than the
    most relevant ones, every time.

    BM25 answers "how unusual is this word here, given how long this section is
    and how often the word occurs across the filing". Its two constants are the
    standard ones and it is a dozen lines of arithmetic, which matters more than
    the ranking quality: a verifier that cannot recompute a score cannot audit
    it.

A SECTION THAT DOES NOT CONTAIN A QUERY TERM SCORES ZERO AND IS DROPPED
    Returning the best of a bad set, unranked and unlabelled, is how an agent
    ends up quoting a section about executive compensation in answer to a
    question about debt covenants. An empty result is a valid answer
    (docs/mcp-tools.md).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from schema.contracts.common import ISODate
from schema.contracts.filings import FilingSection

K1 = 1.5
"""BM25 term-frequency saturation, the standard value. The fifth occurrence of
a word says much less than the second, and past roughly K1 occurrences extra
ones stop moving the score. Without it the longest section wins every query."""

B = 0.75
"""BM25 length normalization, standard. 0 ignores length entirely (Item 1A wins
everything); 1 divides it out completely (a one-line heading beats a section
that genuinely discusses the term). 0.75 is the usual compromise."""

_TOKEN = re.compile(r"[a-z0-9]+")

MIN_TOKEN_LENGTH = 2
"""Single characters carry no signal and match everywhere."""

STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those of in on at to for
    with without from by as is are was were be been being it its we our us they
    their he she his her you your i not no do does did have has had will would
    can could shall should may might must
    """.split()
)
"""Only the closed-class words. Nothing domain-specific: "risk", "debt" and
"revenue" are exactly what someone searches a filing for, and a stoplist that
learned from the corpus would make the ranking depend on which filings happened
to be loaded."""


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric runs, minus stopwords. Deterministic and boring."""
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) >= MIN_TOKEN_LENGTH and token not in STOPWORDS
    ]


@dataclass(frozen=True)
class Hit:
    """One section and why it ranked where it did."""

    section: FilingSection
    score: float
    matched_terms: tuple[str, ...]

    @property
    def section_id(self) -> str:
        return self.section.section_id


@dataclass
class Index:
    """An in-memory BM25 index over one caller's sections.

    Built per search rather than cached: a company's sections are already in
    memory by the time anything searches them, tokenizing a few megabytes costs
    milliseconds, and a cached index is a correctness problem the moment a new
    filing lands. If that ever stops being true, the fix is a cache here, not a
    different interface.
    """

    sections: list[FilingSection]
    texts: list[str]

    def __post_init__(self) -> None:
        self._tokens = [tokenize(t) for t in self.texts]
        self._counts = [Counter(t) for t in self._tokens]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_length = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._doc_freq: Counter[str] = Counter()
        for counts in self._counts:
            self._doc_freq.update(counts.keys())

    def _idf(self, term: str) -> float:
        """How unusual the term is across these sections.

        The +0.5 smoothing is BM25's: a term present in every section gets an
        idf near zero rather than a negative one, so a common word cannot push a
        section DOWN the ranking.
        """
        n = len(self.sections)
        df = self._doc_freq.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, index: int, terms: list[str]) -> tuple[float, tuple[str, ...]]:
        counts = self._counts[index]
        length = self._lengths[index]
        total = 0.0
        matched: list[str] = []
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            matched.append(term)
            norm = 1 - B + B * (length / self._avg_length if self._avg_length else 1.0)
            total += self._idf(term) * (tf * (K1 + 1)) / (tf + K1 * norm)
        return total, tuple(dict.fromkeys(matched))

    def search(self, query: str, limit: int = 10) -> list[Hit]:
        """Sections containing at least one query term, best first."""
        terms = tokenize(query)
        if not terms:
            return []
        hits = []
        for i, section in enumerate(self.sections):
            score, matched = self.score(i, terms)
            if score <= 0:
                continue
            hits.append(Hit(section=section, score=score, matched_terms=matched))
        # section_id breaks ties so two runs over the same corpus agree; without
        # it the order depends on how the sections happened to be loaded.
        hits.sort(key=lambda h: (-h.score, h.section.section_id))
        return hits[:limit]


def matches_filters(
    section: FilingSection,
    *,
    as_of: ISODate | None,
    forms: list[str] | None,
    items: list[str] | None,
) -> bool:
    """Scope before ranking. `as_of` is not optional in the tool above this."""
    if as_of and section.filed_at > as_of:
        return False
    if forms and str(section.form) not in {str(f) for f in forms}:
        return False
    if items and str(section.item) not in {str(i) for i in items}:
        return False
    return True


def search(
    sections: list[FilingSection],
    texts: list[str],
    query: str,
    *,
    as_of: ISODate | None = None,
    forms: list[str] | None = None,
    items: list[str] | None = None,
    limit: int = 10,
) -> list[Hit]:
    """Filter, then rank.

    Scoping first means the idf reflects what was searchable at `as_of` rather
    than what exists today - two runs of the same backtest over a corpus that
    has since grown must rank the same way.
    """
    kept = [
        (section, text)
        for section, text in zip(sections, texts, strict=True)
        if matches_filters(section, as_of=as_of, forms=forms, items=items)
    ]
    if not kept:
        return []
    index = Index([s for s, _ in kept], [t for _, t in kept])
    return index.search(query, limit=limit)
