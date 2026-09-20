# P1 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 2 complete. **The MCP server is live in mock mode and P3 is unblocked.**
**Next:** [roadmap](../roadmap.md) Step 3 — the XBRL concept map and normalization,
then `search_filings` / `get_filing_section`, which is what P3 is waiting on.
**Blockers:** none.

| Capability | State | Notes |
|---|---|---|
| **MCP server** | **mock, live over MCP** | 5 of 10 tools served over the in-memory transport |
| `get_financial_facts` | **served** | as_of + restatement filtering, `periods`, `include_superseded` |
| `get_market_snapshot` | **served** | null before the snapshot was observed |
| `get_company_profile` | **served** | |
| `get_peer_companies` | **served** | `limit` + `truncated` |
| `resolve_fact` | **served** | flags `is_superseded` / `is_future` separately |
| `search_filings` | not served | **Step 3 — P3's top ask**; needs `FixtureFilingRepository` |
| `get_filing_section` | not served | **Step 3 — P3's top ask** |
| `search_filing` | not served | Step 3 |
| `search_news` | not served | Step 4 |
| `calculate_valuation` | not served | Step 4; waits on P2's `calc.api` |
| **EDGAR client** | **real** | submissions, filings, documents; responses replayed in tests |
| **ticker → CIK** | **real** | `BRK.B` / `BRK-B` / `brk-b` all normalise |
| **rate limiting** | **real** | token bucket at 8 req/s; escalating 429/503 backoff |
| **on-disk cache** | **real** | by accession for filings; `get_fresh()` for the ticker map |
| **`SEC_USER_AGENT` loading** | **real** | `data/ingest/env.py`; refuses a UA with no contact details |
| `check_scope` | mock | ACME in scope, BANKX rejected; real SIC classification is Step 3 |
| `build_factsheet` | mock | returns the ACME fixture; **P3's auditor needs a real one** |
| XBRL concept mapping | not started | Step 3; map drafted in `normalize/concept_map.py` |
| YTD differencing / Q4 derivation | not started | Step 3 |
| Restatement linking | not started | Step 3; one restatement exists in the fixtures |
| Section parsing | not started | Step 3 |
| Postgres store | not started | migration file lists the tables |
| `fixtures/real/` demo tickers | not started | Step 6; coordinate the choice via `docs/requests/` |

**Last updated:** 2026-09-19 (Step 2: EDGAR client, rate limiting, cache, ticker→CIK)

---

## Two findings from real SEC data that change Step 3's design

Fetched for AAPL, JPM, TSM, RDDT, O, CRCL and FIG before writing any
classification. Both of these would have produced a confident wrong answer.

1. **`filings.recent` is a window, not a history.** JPM's holds 26,190 filings
   but spans **one year** and contains a single 10-K, with 70 overflow pages
   behind it. Counting annual reports there would classify JPM as "not enough
   history". Counting distinct fiscal years in `companyfacts` gives 17. The
   scope check must use `companyfacts`; `list_filings` documents the limit.

2. **TSM has no `us-gaap` taxonomy at all — only `ifrs-full`.** A 20-F filer
   reports under IFRS, so a us-gaap concept map returns *nothing* for it. The
   planned "partial: foreign issuer" label understates this: without an
   `ifrs-full` map the factsheet would be empty rather than reduced. Step 3
   needs to decide whether to map IFRS or to refuse 20-F filers outright.

---

## For P3: the tools are live

```python
import anyio
from mcp import Client
from mcp_server.server import build_server

async def main():
    async with Client(build_server()) as client:
        result = await client.call_tool(
            "get_financial_facts",
            {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2026-09-19"},
        )
        print(result.structured_content)

anyio.run(main)
```

`mcp_server.server.IMPLEMENTED_TOOLS` is the authoritative list of what is
served today. The other five are in the contracts but deliberately not
advertised — an agent planning around a tool that raises `NotImplementedError`
is worse off than one that knows the tool is absent.

Tickers in mock mode: `ACME` (in scope) and `BANKX` (exercises the rejection path).

### What the tools guarantee

- **`as_of` is required on every data tool**, enforced by the contract models.
  Nothing filed or observed after it can appear in a response.
- **Restatements are point-in-time.** ACME's FY2024 operating cash flow reads
  690M before 2026-02-20 and 700M from 2026-02-20, and the corrected figure
  never leaks backwards into an earlier run.
- **Failures come back as MCP errors with a readable message**, not as protocol
  exceptions — an out-of-scope ticker names itself and gives a reason.
- **`resolve_fact` distinguishes three cases** the verifier needs kept apart:
  the id does not exist (`fact: null`), it was restated (`is_superseded`), or it
  post-dates the run (`is_future`).
- **The advertised input schema is generated from the contract model** that
  validates the call, so the two cannot drift apart.
- **Read-only.** No tool writes.

## Design notes

**Low-level `Server`, not `MCPServer`.** The tool schema is generated from
`schema.contracts.tools`, not from a python function signature. With
`MCPServer`'s decorator the advertised schema comes from the signature, so a
contract change would silently stop matching what validates the call — the one
failure P3 cannot diagnose from their side of the protocol.

**`truncated` is computed, not guessed.** `get_financial_facts` fetches unsliced
and compares; `get_peer_companies` asks for `limit + 1`. Otherwise "exactly
`limit` rows" and "more than `limit` rows" would be indistinguishable, and
"few comparables exist" is a data-quality signal worth keeping.

**`is_superseded` is relative to `as_of`, not to today.** The as-filed FY2024
cash flow was the current figure until the FY2025 10-K restated it, so a run
dated before that must not be told it cited a corrected number (ADR 0003).

## Environment

The MCP SDK needs **Python ≥ 3.10**; this machine's `/usr/bin/python3` is 3.9.6.

```bash
/opt/anaconda3/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r mcp_server/requirements.txt \
                                 -r data/requirements.txt \
                                 -r tests/contracts/requirements.txt ruff
make lint test-contracts PY=.venv/bin/python
.venv/bin/python -m pytest mcp_server/tests -q      # 42 passed
```

`.venv/` is gitignored. The Makefile's `PY ?= python` already allows this, so no
repo change is needed.

## Known issues

1. **`make test` fails to collect on a clean main** — five identically-named
   `test_placeholders.py` modules collide. Filed as
   `docs/requests/2026-09-19-p1-to-coordinator-make-test-collection.md`;
   `make test-contracts` is unaffected.
2. **`resolve_fact`'s stub docstring said "KeyError for an unknown fact_id"**,
   which contradicts both `docs/mcp-tools.md` and the Step 1 test. The spec
   wins: an unknown id returns `fact: null`. Docstring corrected.
