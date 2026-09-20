# P1 -> coordinator: `docs/sec-pitfalls.md` 1 overstates the companyfacts trap

**From:** P1 (`data/`, `mcp_server/`)  **To:** coordinator, P2, P3
**Urgency:** low. Nothing is broken; the doc just prescribes a remedy that costs
20x the requests it needs to, and P1 has built the cheaper one.

## What the doc says

> The SEC's `companyfacts` endpoint returns the **latest** value for every
> concept. [...] **The fix.** For any run with an `as_of`, use per-filing XBRL
> (`companyconcept`), which carries the accession and filing date of each value.

## What the payload actually contains

Checked against AAPL, MSFT, NVDA, AMZN, GOOGL, KO, WDFC, JPM, O and TSM.
`companyfacts` keeps **every filed version of every period**, each carrying its
own `accn` and `filed`. NVDA's fiscal year ending 2023-01-29 appears three
times, from the FY2023, FY2024 and FY2025 10-Ks:

```
end=2023-01-29  fy=2023  accn=0001045810-23-000017  filed=2023-02-24
end=2023-01-29  fy=2024  accn=0001045810-24-000029  filed=2024-02-21
end=2023-01-29  fy=2025  accn=0001045810-25-000023  filed=2025-02-26
```

So the endpoint is point-in-time capable. The trap is narrower than the doc
states: it bites code that takes the **last entry per period without reading
`filed`**, which is the obvious way to write it and would silently produce the
restated number.

## Why it matters

`companyconcept` is one request per tag. The concept map asks for ~40 tags, so a
single company would cost ~40 requests against an 8 req/s budget, versus **one**
for companyfacts. For a demo fetching several tickers that is the difference
between a snappy run and a rate-limited one.

## What P1 built

`data/normalize/to_facts.py` reads `filed` on every entry and drops anything
filed after `as_of`; `data/normalize/restatements.py` keeps each earlier version
as its own row with `superseded_by` set. `as_known_on(facts, date)` reproduces
the view from any past date. The real restatements in the data are stock splits
(NVDA 10-for-1, AMZN and GOOGL 20-for-1), and the tests assert that a run dated
before a split sees the pre-split share count.

`data/ingest/companyfacts.py::fetch_concept` stays for the cases companyfacts
cannot serve: a truncated history, or a dimensioned disclosure.

## Ask

Reword `docs/sec-pitfalls.md` 1 from "never use companyfacts for a historical
run" to "never take the last entry per period — read `filed` on every entry".
The ADR 0003 guarantee is unchanged, and no partition needs a code change.

P1 cannot edit that file (it is outside the partition), hence this request.
