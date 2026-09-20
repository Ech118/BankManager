# P1 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 4 in progress. **Nine of eleven tools are served; XBRL normalization
is real and runs against twelve recorded filers.**
**Next:** `build_factsheet` live plus recordings, then the last two tools. Real 10-K section extraction is deferred and is
what `search_filing` needs to work in live mode.
**Blockers:** `get_factsheet` is in the contracts but not yet in `main` -
PR #2 (`contracts/get-factsheet-tool`) needs coordinator approval.

| Capability | State | Notes |
|---|---|---|
| **MCP server** | **mock, live over MCP** | 9 of 11 tools served over the in-memory transport |
| `get_financial_facts` | **served** | as_of + restatement filtering, `periods`, `include_superseded` |
| `get_market_snapshot` | **served, live** | Finnhub price + filing share count; degrades to price unavailable |
| `get_company_profile` | **served** | |
| `get_peer_companies` | **served, live** | SIC + XBRL frames ranking; `limit` + `truncated` |
| `resolve_fact` | **served** | flags `is_superseded` / `is_future` separately |
| `search_filings` | **served** | newest first, `forms` filter, `limit` + `truncated` |
| `get_filing_section` | **served** | verbatim; errors on unknown id AND on one filed after `as_of` |
| `search_filing` | **served** | BM25 over whole sections, in process; **live needs the section parser** |
| `search_news` | not served | Step 4 |
| `calculate_valuation` | not served | Step 4; waits on P2's `calc.api` |
| **EDGAR client** | **real** | submissions, filings, documents; responses replayed in tests |
| **ticker → CIK** | **real** | `BRK.B` / `BRK-B` / `brk-b` all normalise |
| **rate limiting** | **real** | token bucket at 8 req/s; escalating 429/503 backoff |
| **on-disk cache** | **real** | by accession for filings; `get_fresh()` for the ticker map |
| **`SEC_USER_AGENT` loading** | **real** | `data/ingest/env.py`; refuses a UA with no contact details |
| `check_scope` | **real** | three levels: supported / partial / unsupported. Mock path unchanged |
| `build_factsheet` | mock | returns the ACME fixture; **P3's auditor needs a real one** |
| `get_factsheet` | **served** | new tool (SCHEMA_VERSION 2.1.0); P3 can drop the injected factsheet |
| XBRL concept mapping | **real** | per-PERIOD chains, us-gaap; `ifrs-full` slot present and empty |
| Annual normalization | **real** | 5 fiscal years of 10-K values -> `FinancialFact` |
| Fiscal year labelling | **real** | from the filer's own numbering; Jan/Jun/Aug/Sep year ends tested |
| Total debt | **real** | derived fact; components emitted and linked by `Derivation` |
| Restatement linking | **real** | `superseded_by` + `as_known_on()`; real splits exercise it |
| Stock splits | **real** | discontinuity detector + split-adjusted derived facts when a ratio is tagged |
| Derived-fact dating | **real** | `filed_at` = latest input's, never null; `data/normalize/derived.py` |
| Peer selection | **real** | browse-edgar SIC (paged) + frames revenue ranking, log-distance cutoff, provider fallback |
| `sp500_baseline` | **real** | SPY quote measured; forward P/E, earnings yield and risk-free rate are reviewed constants typed `assumption` |
| Market client | **real** | `MarketClient` Protocol; Finnhub impl; 5-min quote cache; `NullMarketClient` for outages |
| Shares outstanding | **real** | 5-candidate chain behind a public-float floor check (GOOGL, BRK-B) |
| Market snapshot | **real** | one timestamp for the bundle; EV bridge cites the facts |
| Point-in-time reads | **real** | facts filed after `as_of` are never read |
| YTD differencing / Q4 derivation | not started | annual only for now; both raise rather than guess |
| ticker -> CIK overrides | **real** | `data/ingest/ticker_overrides.py`; XOM is the only one in the top 100 |
| `fixtures/real/` recorded filers | **real** | 12 companies, trimmed companyfacts + submissions |
| Section parsing | mock | serves `fixtures/mock/sections/*.txt`; **real 10-K Item extraction is the gap that keeps `search_filing` mock-only in live mode** |
| Postgres store | not started | migration file lists the tables |
| `fixtures/real/` demo tickers | not started | Step 6; coordinate the choice via `docs/requests/` |

**Last updated:** 2026-09-20 (derived-fact dating, baseline, `search_filing`, live peers)

---

## What twelve real filers changed about the design

Surveyed AAPL, MSFT, NVDA, AMZN, GOOGL, KO, WDFC, JPM, O, TSM, XOM and BRK.B
before writing the concept map. Seven findings, each of which would have
produced a confident wrong number rather than an error.

1. **A chain must resolve per FISCAL PERIOD, not per company.** NVDA's capex is
   `PaymentsToAcquirePropertyPlantAndEquipment` for FY2010-FY2012 and
   `PaymentsToAcquireProductiveAssets` from FY2022; AAPL's revenue tag changes in
   FY2018; KO stopped tagging `LongTermDebt` after FY2023. A chain resolved once
   per company loses years.

2. **`fy` on a companyfacts entry is the FILING's fiscal year, not the fact's.**
   NVDA's year ending 2023-01-29 carries `fy` 2023, 2024 and 2025, because later
   10-Ks repeat it as a comparative. The filer's own label is the `fy` of the
   EARLIEST-filed 10-K entry for that period. That gives FY2026 for NVDA's
   January year end and FY2025 for WD-40's August one, with no calendar guessing.

3. **companyfacts is point-in-time capable, contradicting docs/sec-pitfalls.md 1.**
   It keeps every filed version, each with its own `accn` and `filed`. The trap is
   narrower than "never use companyfacts": it bites code that takes the last entry
   per period without reading `filed`. One fetch per company therefore replaces
   ~20 companyconcept requests. Filed as
   `docs/requests/2026-09-19-p1-to-coordinator-companyfacts-is-point-in-time.md`.

4. **companyfacts carries no dimensioned facts at all.** Across four filers the
   union of entry keys is exactly `accn, end, filed, form, fp, frame, fy, start,
   val`. Company totals are safe by construction - and a dimensioned-only
   disclosure VANISHES rather than arriving sliced, which is how GOOGL loses
   `dei:EntityCommonStockSharesOutstanding` entirely (it tags per share class).

5. **Debt double-counting is real.** NVDA tags `DebtCurrent` and
   `LongTermDebtCurrent` as the same 999M, and `LongTermDebt` already contains
   both; summing naively overstates by 12%. `LongTermDebtAndCapitalLeaseObligations`
   is NONCURRENT (KO's FY2023 value equals `LongTermDebtNoncurrent`, not the
   total). Hence disjoint buckets with a `covers_current` flag.

6. **XOM resolves to a company with no history.** `company_tickers.json` maps XOM
   to ExxonMobil Holdings Corp (CIK 2115436), registered in 2026, zero 10-Ks.
   `data/ingest/ticker_overrides.py` redirects it to CIK 34088. An audit of the
   100 largest US companies (`python -m data.record.cik_history`) found **no other
   ticker** needing an override; the one other miss, MMC, is simply a ticker that
   no longer exists (Marsh & McLennan now files as MRSH).

7. **The restatements in real data are stock splits.** NVDA's 10-for-1 (FY2024
   diluted shares 2,494M -> 24,940M), AMZN's and GOOGL's 20-for-1. A run dated
   before the split must see the pre-split count, which is exactly what
   `restatements.as_known_on()` now reproduces.

8. **A split leaves a five-year series inconsistent while every value in it is
   correct.** A 10-K restates only the two comparative years it shows, so NVDA's
   FY2022 - already out of that window when the 2024 split landed - was never
   restated. Diluted EPS reads 3.85 -> 0.17 -> 1.19 across FY2022-FY2024, and a
   five-year EPS CAGR from it is wrong by 10x. `data/normalize/splits.py` raises
   a data_quality gap at the boundary, and where the filer tagged
   `StockholdersEquityNoteStockSplitConversionRatio1` it also emits
   `eps_diluted_split_adjusted` / `shares_diluted_split_adjusted` as DERIVED
   facts citing the ratio fact and the as-filed fact. The as-filed facts are
   never rewritten. Two traps inside that: the ratio is tagged as an instant by
   one filer and a month-long DURATION by another (NVDA does both), and the same
   split is tagged twice, at announcement and at effect - 164 days apart for
   GOOGL - which would compound 20 into 400.

9. **A cover-page share count cannot be trusted for a multi-class filer.**
   GOOGL's `dei:EntityCommonStockSharesOutstanding` is ABSENT from companyfacts
   (tagged per class, so dimensioned, so dropped). BRK-B's is PRESENT and reads
   941,481 - Class A alone, which at a Class B price makes Berkshire a $480M
   company against its own reported $903B float. Finnhub repeats the same
   mistake (`shareOutstanding` 1.44M); only its `marketCapitalization` covers
   every class. `data/normalize/shares.py` therefore tries five candidates and
   keeps the first that survives a public-float floor check. AAPL, NVDA and
   GOOGL market caps come out equal to the provider's to the dollar.

10. **A derived fact copied from one of its inputs inherits the wrong date.**
    The split-adjusted facts were `model_copy` of the as-filed fact, so they
    carried the as-filed `filed_at`. NVDA's FY2022 EPS was filed 2024-02-21 and
    the 10-for-1 ratio first tagged 2025-05-28, so a run anywhere in those
    fifteen months saw a split-adjusted number computed from a ratio that was
    not yet in the data. The rule is now one function
    (`data/normalize/derived.py`): a derived fact's `filed_at` is the LATEST
    `filed_at` among its inputs, never null, and it carries that filing's
    accession so the two agree. Total debt already followed the rule
    implicitly; it now calls the same helper. Raised with P3 and P2 in
    `docs/requests/2026-09-19-p3-report-inputs-response.md`.

11. **browse-edgar does not support a SIC prefix, and does not order by size.**
    `SIC=35` returns ZERO rows - it is read as an unknown code, not a wildcard -
    so the planned "widen to the two-digit prefix" step would have looked
    correct, never fired, and quietly left every short peer set short. Widening
    the SIZE tolerance replaces it. Separately, a SIC page caps at 100 rows
    ordered by neither size nor relevance: SIC 6021 puts Bank of America on
    page 1, Citigroup on page 2 and Wells Fargo on neither, and SIC 2080 has
    PepsiCo on page 2. Peer selection pages four deep.

12. **Three findings that each produced a plausible wrong peer set.**
    (a) SIC alone is not enough: Apple's SIC 3571 holds Dell at 3.7x revenue and
    then Socket Mobile at 27,600x. Without a distance cutoff a $200M company
    lands in Apple's peer median. (b) Banks tag `RevenuesNetOfInterestExpense`
    and nothing else - its CY2025 frame holds 42 companies - so without that
    concept every bank has no revenue, every candidate is dropped, and JPM's
    ranking silently returns nothing. (c) Inverting SEC's ticker -> CIK map
    naively keeps whichever ticker the iteration ended on, which put `SMCIP`
    (a preferred) and `BSQKZ` in peer sets instead of the common stock; a market
    cap read off a thinly traded preferred is not the company's.

### Two earlier findings, still true

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
served today. The other three are in the contracts but deliberately not
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
- **A missing section is an error, not an empty result.** `get_filing_section`
  errors for an unknown `section_id` and, separately, for one filed after
  `as_of` — returning nothing would look like the filing did not exist.
- **Truncation keeps the offsets honest.** `max_chars` moves `text`, `char_end`
  and `char_count` together, so `char_end - char_start == char_count ==
  len(text)` still holds, and the truncated text is a verbatim prefix.
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
.venv/bin/python -m pytest mcp_server/tests -q      # 73 passed
```

`.venv/` is gitignored. The Makefile's `PY ?= python` already allows this, so no
repo change is needed.

## Known issues

1. **`make test` fails to collect on a clean main** — six identically-named
   `test_placeholders.py` modules collide (`agents/`, `audit/`, `calc/`, `data/`,
   `orchestrator/`, `tests/e2e/`). `data/tests/__init__.py` fixes P1's; the rest
   are other partitions' files. Filed as
   `docs/requests/2026-09-19-p1-to-coordinator-make-test-collection.md`;
   `make test-contracts` is unaffected.
2. **`resolve_fact`'s stub docstring said "KeyError for an unknown fact_id"**,
   which contradicts both `docs/mcp-tools.md` and the Step 1 test. The spec
   wins: an unknown id returns `fact: null`. Docstring corrected.
