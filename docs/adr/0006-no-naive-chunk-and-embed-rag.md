# ADR 0006 — No naive chunk-and-embed RAG

**Status:** accepted (Step 0)

## Context

The default move for "let an agent search filings" is to chunk every document
into overlapping windows, embed them, and retrieve by cosine similarity.

For SEC filings specifically, that throws away something valuable and then tries
to recover it statistically.

**Filings already have structure the SEC mandates.** Item 1A is risk factors.
Item 7 is MD&A. Note 9 is debt. An agent that wants the debt note can ask for
the debt note. Chunking discards that and hopes an embedding rediscovers it.

**Chunk boundaries cut through meaning.** A covenant and the ratio it applies to
land in different windows; a retrieved fragment reads as more alarming, or less,
than the paragraph it came from.

**The corpus is tiny.** Scoped to one company and a date, the candidate set is a
handful of sections — not a corpus that needs approximate nearest-neighbour
search.

**Verification needs stable anchors.** `unsupported_claim` string-matches a
quote inside a cited section. A chunk id is not a stable anchor; a section id
with character offsets is.

## Decision

**Filings are parsed by structure (10-K/10-Q Items, notes), and search starts as
Postgres full-text search scoped by ticker, form, item and date.**

- `data/sections/parser.py` splits on Items and notes, keeping character offsets
  into the source document.
- `FilingSection` carries `section_id`, `item`, `heading_path` and offsets.
- `search_filing` scopes **first**, then ranks with `ts_rank`.
- Search returns **whole sections**, never fragments.
- Agents can also request a section directly by name, which is usually what they
  want.

## Consequences

**Good**

- Retrieval is inspectable: a reviewer can see exactly which section was
  returned and why.
- Quotes anchor to a stable id plus offsets, so verification works.
- No embedding model, no vector store, no index to rebuild.
- Scoping first means keyword search is sufficient — the ranking problem
  disappears once the candidate set is small.

**Costs**

- Section parsing is real work, and filings are messy HTML. Heading patterns
  need maintenance.
- Keyword search misses pure synonym matches. Mitigated by scoping and by agents
  usually knowing which section they want.
- Whole sections cost more tokens than fragments. Mitigated by `max_chars` and
  per-agent tool sets.

## Revisit when

There is a concrete case where scoped structural search demonstrably fails —
not because embeddings are the expected approach.

## Addresses

Design choice recorded in `archive/plan.txt` §4 ("give agents whole filing
sections, not embeddings"), now with reasoning attached.
