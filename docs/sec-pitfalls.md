# SEC data pitfalls

The traps P1 absorbs so that nothing else in the system has to know about them.

Every one of these produces a plausible-looking wrong number rather than an
error, which is what makes them dangerous.

---

## 1. Restatements: `companyfacts` returns today's numbers

The SEC's `companyfacts` endpoint returns the **latest** value for every
concept. When a company restates a prior year, `companyfacts` quietly returns
the corrected figure with no indication that it changed.

**Why it matters.** A backtest run "as of June 2025" that pulls FY2024
operating cash flow from `companyfacts` gets the value as corrected in February
2026. The pipeline then reasons about a number that did not exist at the time.
The backtest looks fine and is worthless.

**The fix.** For any run with an `as_of`, use per-filing XBRL
(`companyconcept`), which carries the accession and filing date of each value.
For each fiscal period, keep the value from the latest filing **filed on or
before `as_of`**.

**The model.** Both rows are kept. The superseded one gets `superseded_by`
pointing at its replacement; nothing is deleted. This is what lets two questions
have different answers:

- "What is FY2024 operating cash flow?" → the current, restated fact
- "What did we know on 2025-06-01?" → the as-filed fact

A system that keeps only the latest value cannot answer the second.

The ACME fixture carries exactly one restatement — FY2024 operating cash flow,
filed at $690M, restated to $700M — so this path is exercised from day one.

---

## 2. Cash flow in a 10-Q is year-to-date

A quarterly cash flow statement covers from the **start of the fiscal year**,
not the quarter.

**Why it matters.** Q3's statement shows nine months of operating cash flow.
Treating it as quarterly overstates cash generation by roughly 3×, and the error
grows through the year — so it is largest in Q3, which is exactly when someone
notices the company looks unusually cash-generative.

**The fix.** Difference successive YTD values. Q1 passes through unchanged; each
later quarter is that quarter's YTD minus the previous quarter's YTD.

Affects: `op_cash_flow`, `capex`, `sbc`, `depreciation_amortization` — and
therefore free cash flow, FCF margin, FCF yield and conversion.

---

## 3. There is no Q4 filing

A company files three 10-Qs and one 10-K. There is no fourth quarterly report.

**Why it matters.** Code that assumes four quarterly filings silently loses a
quarter — usually the strongest one for seasonal businesses.

**The fix.** Derive it: `Q4 = FY - nine-month YTD`. The result is a **derived**
fact with a `Derivation` naming both inputs, so the verifier can recompute it
rather than taking it on trust.

---

## 4. Concept tag variance

The same economic quantity is tagged differently by different filers, and by the
same filer across years. Revenue alone appears as
`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`,
`RevenueFromContractWithCustomerIncludingAssessedTax`, or `SalesRevenueNet`.

**Why it matters.** A single hard-coded tag returns nothing for most companies.
"Nothing" that becomes `0` produces infinite margins and negative growth rates.

**The fix.** An ordered candidate list per canonical metric
(`data/normalize/concept_map.py`). Try each in turn, and **record which one
matched** on the fact's `xbrl_concept`, so a reviewer can see where a number
really came from.

A metric that resolves to nothing becomes an `unavailable` fact plus a
`data_quality` gap. Never `0`.

---

## 5. Dimensions vs consolidated totals

An XBRL fact may be dimensioned — sliced by segment, geography or product line —
or consolidated.

**Why it matters.** Summing dimensioned facts to reconstruct a total is wrong in
at least three ways: axes overlap, some segments are omitted, and
inter-segment eliminations are missing. The result is close enough to look
right.

**The fix.** The consolidated total is the fact with **no** dimensions. Only
that one may be used as a company-level number. Dimensioned facts are kept for
segment analysis and never summed into a total.

---

## 6. SEC User-Agent and rate limits

EDGAR requires a descriptive `User-Agent` including contact details, and
throttles above roughly 10 requests per second.

**Why it matters.** An anonymous or aggressive client gets blocked — typically
during a demo, and typically for long enough to matter.

**The fix.**

- `SEC_USER_AGENT` must be set. `data/ingest/rate_limit.py` raises at startup if
  it is not, rather than failing obscurely under load.
- Cap at 8 requests/second, below the tolerated ceiling.
- Escalating backoff on 429 and 503.
- **Cache by accession number.** Filings are immutable once published, so an
  accession is a perfect cache key: a cached document can never go stale.
- Pre-fetch the demo tickers into `fixtures/real/` so a demo never depends on
  EDGAR being reachable.

---

## 7. Fiscal years are not calendar years

Period labels come from the filer's own `fiscal_year_end`, never from the
calendar month of the period end. A retailer's "FY2025" may end in January 2026.

Getting this wrong misaligns every year-over-year comparison by one period,
which produces growth rates that are wrong but plausible.

---

## 8. Market data is not immutable

Filings are permanent; prices are not. Market data is cached only with a short
TTL and always carries its observation timestamp.

`MarketSnapshot` bundles price, share count, debt and cash at **one instant** on
purpose. Combining a live price with last quarter's share count corrupts market
cap, and therefore every multiple built on it.

A missing snapshot returns `None`, which becomes an `unavailable` value plus a
`data_quality` gap — never a stale price presented as current.
