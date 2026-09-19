# P1 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 0 complete. **Next:** [roadmap](../roadmap.md) Step 1.
**Blockers:** none.

| Capability | State | Notes |
|---|---|---|
| `check_scope` | mock | ACME in scope, BANKX rejected; real SIC checks are Step 1 |
| `build_factsheet` | mock | returns the ACME fixture |
| point-in-time (`as_of`) | mock | filters fixture periods and sections by filed date |
| `search_filings` | mock | reads `fixtures/mock/filings.json` |
| `get_filing_section` / `get_section_text` | mock | reads `fixtures/mock/sections/*.txt` |
| `search_filing` | mock | naive substring match; Postgres FTS is Step 3 |
| `get_financial_facts` | mock | reads `fixtures/mock/facts.json`, excludes restated |
| `resolve_fact` | mock | |
| `get_market_snapshot` | mock | |
| `get_company_profile` | mock | |
| `get_peer_companies` | mock | |
| `search_news` | mock | |
| EDGAR client | not started | Step 1 |
| XBRL concept mapping | not started | Step 1; map drafted in `normalize/concept_map.py` |
| YTD differencing / Q4 derivation | not started | Step 2 |
| Restatement linking | not started | Step 2; one restatement exists in the fixtures |
| Section parsing | not started | Step 3 |
| Postgres store | not started | Step 1; migration file lists the tables |
| MCP server | not started | Step 1 |
| `fixtures/real/` demo tickers | not started | Step 5; coordinate the choice via `docs/requests/` |

**Last updated:** 2026-09-19 (Step 0 scaffold)
