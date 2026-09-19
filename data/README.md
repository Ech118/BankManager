# data/ — P1 Data & Truth Layer

**Owner: P1.** Only P1 edits this directory. Rules: [docs/p1/CLAUDE.md](../docs/p1/CLAUDE.md).

Produces the **fact sheet** (`schema/factsheet.json`) and the `FinancialFact`
rows behind it. Everything downstream depends on this being right, and on it
being honest about what it does not know.

## Public interface

`data/api.py` only. Other partitions never import a private module here
([docs/adr/0007](../docs/adr/0007-partition-boundaries.md)). `mcp_server/` wraps
these functions as MCP tools; P3 reaches them only that way.

| Function | Returns |
|---|---|
| `check_scope(ticker, as_of=None)` | `{in_scope, reason}` |
| `build_factsheet(ticker, as_of=None)` | `Factsheet` |
| `search_filings(ticker, as_of, forms, limit)` | `list[Filing]` |
| `get_filing_section(section_id, as_of)` | `FilingSection` with text |
| `get_section_text(source_id, as_of)` | `str` (passed into `audit.run_audit`) |
| `search_filing(ticker, query, as_of, ...)` | `list[FilingSection]` |
| `get_financial_facts(ticker, metrics, as_of, ...)` | `list[FinancialFact]` |
| `get_market_snapshot(ticker, as_of)` | `MarketSnapshot` |
| `get_company_profile(ticker, as_of)` | `CompanyProfile` |
| `get_peer_companies(ticker, as_of, limit)` | `list[Peer]` |
| `search_news(ticker, as_of, ...)` | `list[NewsItem]` |
| `resolve_fact(fact_id, as_of)` | `FinancialFact` |

Every read takes an `as_of`. That is not decoration — see
[ADR 0003](../docs/adr/0003-point-in-time-correctness.md).

## Layout

```
ingest/        raw fetching only: EDGAR, XBRL, market, news, rate limiting, cache
normalize/     payloads -> FinancialFact: concept mapping, dimensions, periods,
               restatements, scope
sections/      filings -> FilingSection, split on Items and notes (ADR 0006)
store/         Postgres engine + migrations (MODE=live only)
repositories/  FactRepository / FilingRepository / MarketRepository,
               in postgres_* and fixture_* flavours
```

## Dependencies

`data/requirements.txt`, which includes `schema/contracts/requirements.txt`.
P1 depends on no other partition.

## The four traps this layer exists to absorb

Detail in [docs/sec-pitfalls.md](../docs/sec-pitfalls.md).

1. **Restatements.** `companyfacts` returns today's restated numbers. Using it
   for a historical run leaks the future.
2. **Year-to-date cash flow.** A 10-Q cash flow statement is YTD, not quarterly.
3. **No Q4 filing.** Q4 = FY minus the nine-month YTD figure.
4. **Concept tag variance.** The same quantity is tagged differently by
   different filers and by the same filer across years.
