# P1 — Data & MCP

**Owns:** `data/`, `mcp_server/`, `fixtures/real/`, `docs/p1/`
**Branch:** `p1-data`
**Produces:** the fact sheet (`schema/factsheet.json`) and the `FinancialFact`
rows behind it

## Scope

Everything between a ticker and a trustworthy set of numbers:

- SEC EDGAR ingestion — submissions, XBRL, filing documents
- Normalization — concept mapping, dimensions, period labelling, YTD
  differencing, Q4 derivation, restatements
- Filing-section parsing on Items and notes, with character offsets
- Market data, S&P baseline, news
- Postgres store, migrations, and the repository implementations
- The MCP server that exposes all of it
- ACME mock fixtures and the pre-fetched real demo tickers

## Public interface

`data/api.py`, plus the MCP tools in `mcp_server/`. See
[data/README.md](../../data/README.md) and
[docs/mcp-tools.md](../mcp-tools.md).

## Dependencies

`schema.contracts` only. P1 depends on no other partition.

The single exception in the other direction:
`mcp_server/tools/calculate_valuation.py` imports `calc.api` (P2) and is a
pass-through ([ADR 0007](../adr/0007-partition-boundaries.md)).

## What P1 does not do

- Compute margins, FCF or ratios — that is `calc/`
- Call an LLM
- Know that agents exist

## The four things that will bite

[docs/sec-pitfalls.md](../sec-pitfalls.md) in full, but the short version:

1. `companyfacts` returns **restated** values — never use it for a historical run
2. 10-Q cash flow is **year-to-date**, not quarterly
3. There is **no Q4 filing**; derive it
4. XBRL **concept tags vary** by filer and by year

Each produces a plausible-looking wrong number rather than an error.

## Done when

- Three real tickers produce schema-valid factsheets
- A point-in-time query on a company that restated returns the **as-filed**
  value
- The cache-hit path is proven
- Every failure degrades to `unavailable` plus a `data_quality` gap
- MCP tools respond over both transports
