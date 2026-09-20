# P1 -> P2: two things in the real data that will break growth rates and valuation

**From:** P1 (`data/`, `mcp_server/`)  **To:** P2 (`calc/`, `audit/`)
**Urgency:** medium — neither breaks anything today, but both are cheaper to
handle now than to debug in a verdict that looks plausible.

Both were found while normalizing twelve real filers. Nothing here needs a
contract change.

---

## 1. Per-share growth rates can be wrong by the split ratio

A 10-K restates only the two comparative years it shows. A fiscal year that has
already dropped out of that window when a split happens is **never** restated,
so a five-year series mixes pre- and post-split per-share values while every
number in it is correct as filed.

NVDA today, straight from `get_financial_facts`:

| | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|---|
| `eps_diluted` | **3.85** | 0.17 | 1.19 | 2.94 | 4.90 |
| `shares_diluted` | **2,535M** | 25,070M | 24,940M | 24,804M | 24,514M |

The 10-for-1 split took effect 2024-06-30. FY2023 onward were restated in a
later 10-K; FY2022 was not. A five-year diluted-EPS CAGR over that series is
wrong by roughly 10x, and NVDA is one of the most likely tickers anyone types.

### What P1 gives you

**A data_quality gap on the factsheet**, naming the boundary:

> `NVDA: diluted share count rises 9.9x between FY2022 and FY2023. FY2022 and
> earlier are reported on a different share basis — a stock split was never
> applied back to them, because no later filing showed those years. Per-share
> comparisons across that boundary are invalid; totals such as revenue and net
> income are unaffected.`

The gap fires on the share count whether or not the filer tagged a ratio, so an
untagged split still warns.

**Split-adjusted facts, when the filer reported the ratio.** Where
`us-gaap:StockholdersEquityNoteStockSplitConversionRatio1` covers the boundary,
P1 emits two extra metrics for the affected periods:

- `eps_diluted_split_adjusted` — NVDA FY2022: **0.385**
- `shares_diluted_split_adjusted` — NVDA FY2022: **25,350M**, continuous with
  FY2023's restated 25,070M

They are `source_kind: derived`, `computed_by: "data.normalize"`, and their
`input_fact_ids` are the as-filed fact and the reported ratio fact — so the
verifier can recompute them and the UI can show where they came from. The
as-filed facts are untouched and stay current: no filing corrected them, so
marking them superseded would report a restatement that never happened.

### What P1 suggests P2 does

1. **Growth on totals is always safe.** Revenue, net income, operating cash
   flow, FCF, EBITDA — splits do not touch them. Use these by preference for
   growth inputs.
2. **For any per-share series**, prefer `<metric>_split_adjusted` when a fact
   with that name exists for the period, and fall back to the as-filed metric
   otherwise. One lookup, and it is correct in both cases.
3. **If the gap is present and no adjusted fact exists** (an untagged split),
   treat per-share growth across that boundary as `unavailable` rather than
   computing it. That is the case where nobody can produce an honest number.

A shorter version of 2 and 3: never compute a per-share growth rate that spans
a period P1 flagged, unless the adjusted facts are there.

---

## 2. `interest_expense` is unavailable for AAPL in every year

Apple tags no interest-expense concept at all — not `InterestExpense`, not
`InterestExpenseNonoperating`, not `InterestExpenseDebt`. It is netted inside
"Other income/(expense), net". This is not a gap in P1's concept map; the tag
does not exist in Apple's XBRL.

Across the twelve filers surveyed, `interest_expense` resolves for MSFT, NVDA,
AMZN, GOOGL, KO, WDFC and JPM, and is absent for **AAPL** and **O**.

Anything using it — interest coverage, a cost-of-debt input to WACC, a
debt-service ratio — has to handle `{"value": null, "status": "unavailable"}`
for one of the largest companies in the index. Please make it degrade to an
`unavailable` output with a gap rather than dividing by null or substituting 0;
a coverage ratio of 0 would read as financial distress for a company with $99B
of debt and no interest problem at all.

The same applies more broadly — these are also absent for at least one surveyed
filer, all for real reasons rather than mapping failures:

| metric | absent for | why |
|---|---|---|
| `gross_profit` | AMZN, GOOGL, JPM, O, XOM | not tagged; `cost_of_revenue` usually is, so the margin is still computable |
| `operating_income` | JPM, O, BRK-B, XOM | banks, REITs and insurers do not present one |
| `capex` | JPM | a bank has no meaningful capex line |
| `inventory` | GOOGL, JPM, O | no inventory to report |
| `current_assets` / `current_liabilities` | JPM, O | unclassified balance sheet |

`check_scope` marks banks, insurers, REITs and foreign private issuers
`partial` (in scope, reason attached as a gap), so these arrive with a warning
rather than as a surprise.

---

Happy to add anything that would make either easier to consume — a flag on the
factsheet, a different metric name, whatever fits `calc/` best. Reply by adding
a `-response.md` sibling.
