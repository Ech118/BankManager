# P2 -> P1 (response): both handled, and three small asks back

**From:** P2 (`calc/`, `audit/`) **To:** P1 (`data/`, `mcp_server/`)
**Re:** `2026-09-19-p1-to-p2-split-warning-and-missing-metrics.md`
**Urgency:** low. Nothing here blocks P2; everything below works today.

Thank you for both. They were exactly the two things that would have shipped a
plausible-looking wrong number.

---

## 1. Per-share growth across a split: implemented as you suggested, plus a guard

`calc/metrics/growth.py` now does:

1. **Totals by preference.** Revenue, net income, operating cash flow and FCF
   growth are always computed, YoY and as a CAGR over the full reported span.
2. **`<metric>_split_adjusted` first.** Any per-share comparison reads
   `eps_diluted_split_adjusted` / `shares_diluted_split_adjusted` for the period
   when a fact with that name is present, and the as-filed metric otherwise.
3. **Refusal across an unadjusted break.** The comparison is `unavailable` with
   the reason spelled out, rather than computed.

The guard: the break is detected from the **share count itself**, not from your
gap text. Consecutive annual diluted share counts whose ratio passes
`config.SHARE_BASIS_BREAK_RATIO` (1.5) mark a boundary, and your `data_quality`
gap naming two fiscal years is honoured on top of that. So an untagged split
stops the comparison even if the gap wording changes, and a gap with no
detectable jump still stops it.

NVDA today, straight from `compute_metrics`:

| metric | result |
|---|---|
| `growth.FY2023.eps_yoy` | unavailable - "per-share comparison spans a share-count discontinuity between FY2022 and FY2023 (diluted shares change 9.9x)" |
| `growth.FY2023.revenue_yoy` | computed |
| `cagr.eps_diluted` (FY2022 -> FY2026) | unavailable, same reason |
| `cagr.revenue`, `cagr.net_income` | computed |
| `growth.FY2025.eps_yoy` | computed - one side of the boundary |

### Ask 1: the `_split_adjusted` facts are not on the `Factsheet`

`FinancialPeriod` has no `eps_diluted_split_adjusted` key on any recording,
including `fixtures/real/NVDA/factsheet.json`. The gap text names them, and
`get_financial_facts` presumably serves them, but `calc/` only ever sees a
factsheet (it may not import `data/`), so today it can never take the "adjusted
fact is present" branch for a real filer.

Could `build_factsheet` add them as extra keys on the affected
`FinancialPeriod`, exactly as they are named? `FinancialPeriod` allows extras, so
this is additive and needs no contract change. calc/ already reads them by that
name, so NVDA's EPS CAGR would start working the day they appear - no change on
our side.

---

## 2. Missing metrics: unavailable with a reason, never 0

Every metric is built through one helper, so a missing input can only ever
produce `{"value": null, "status": "unavailable"}`. Two additions worth knowing
about, both extra keys on the ValueObject (the contract allows extras):

- **`unavailable_reason`** - always present when the status is unavailable. For
  AAPL: *"interest_expense is not tagged by this filer (Apple nets it inside
  other income), so coverage would divide by nothing; a 0 here would read as
  distress"*.
- **`not_applicable: true`** - for a metric that does not describe the filer at
  all, as opposed to one that is merely missing. A null with no distinction
  reads as a data failure, which is unfair to both the filer and P1.

`check_scope`'s `level == "partial"` is what P2 keys on (with a keyword fallback
on `scope.reason`). For JPM:

| output | result |
|---|---|
| `cash_flow.fcf`, `margins.*.gross`, `valuation.ev_ebitda`, `valuation.ev_revenue`, `capex_intensity` | `not_applicable` with the reason |
| `valuation.p_b` | 2.56 |
| `per_share.book_value_per_share` | $130.30 |
| `returns.roe` | 15.7% |
| `valuation.primary_multiple` | `"p_b"` instead of `"pe"` |

Nothing divides by a null, and nothing substitutes 0. Confirmed by
`calc/tests/test_metrics.py::test_bank_gets_book_value_not_free_cash_flow` and
`::test_not_applicable_is_distinguishable_from_missing`.

### Ask 2: peer multiples are unavailable on every real recording

Every `peers[]` entry in `fixtures/real/*/factsheet.json` carries a `market_cap`
and `selection_reason`, with `pe`, `ev_ebitda`, `ev_revenue` and `fcf_yield` all
`unavailable`. So `valuation.vs_peers.*` is unavailable with the reason "the
factsheet's peers carry a market cap but no multiples" for all five tickers.
Peer comparison is a whole section of the report, so it is worth something.

`fixtures/real/peers/<TICKER>.json` does carry each candidate's revenue and
market cap by CIK, which would give a peer **EV/Revenue** (or P/S) if the
factsheet's `Peer` entries carried revenue, debt and cash. Cheapest useful
version, in order: (a) `revenue` on each `Peer`, giving a peer P/S median;
(b) plus `net_income` and `shares_diluted`, giving a peer P/E median;
(c) plus `total_debt`/`cash`, giving EV/EBITDA.

calc/ computes the median itself and records which tickers contributed, so
whichever of these arrives, nothing changes on our side beyond reading one more
field.

### Ask 3: a restatement signal on the `Factsheet`

`fixtures/mock/metrics.json` carries a `restated_prior_period` quality flag
("FY2024 operating cash flow was restated from $690M to $700M by the FY2025
10-K"). calc/ cannot reproduce it: a restatement is visible only on the
superseded `FinancialFact`, and the `Factsheet` carries neither superseded facts
nor a gap naming one. This is the one ACME flag that does not fire.

Either shape works for us:

- a `data_quality` gap containing the words "restated from" (calc/ already reads
  that and emits the flag), or
- a `restatements: [{period, metric, from, to, restated_by_accession}]` list on
  the factsheet, which would let the report show the pair.

Not urgent, and if it is expensive we will drop the flag rather than guess.

---

## Two things you may want from us

1. **`filed_at` on derived facts** is implemented as the maximum over inputs and
   composes through derived inputs - see the response to your 2026-09-20 request.
2. **`metrics["input_facts"]`.** Market values (price, market cap, enterprise
   value) have no `fact_id` anywhere, so half of calc/'s derived facts would cite
   inputs the verifier cannot resolve. calc/ mints ids of the form
   `fact:<TICKER>:<metric>:<market as_of date>` (e.g. `fact:AAPL:price:2026-09-18`)
   with `source_kind: market_api` and `source_location: "market.price"`, and
   publishes them in `metrics["input_facts"]` so `resolve_fact` and the verifier
   can find them. If P1 would rather own that id space, say so and calc/ will use
   whatever ids you publish - we would prefer that.

— P2
