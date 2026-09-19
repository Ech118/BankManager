# Data model

The financial truth layer: what a fact is, where it comes from, and what may be
done with it.

Source of truth: `schema/contracts/` (pydantic). `schema/*.json` is generated
from it by `make gen-schema`.

---

## The principle

**Every number lives in a normalized facts store with provenance, and agents
cite `fact_id`s, never bare numbers.**
([ADR 0002](adr/0002-financial-truth-layer.md))

There is no way to construct a `FinancialFact` that cannot be traced back to a
filing, an API response, or an explicit derivation. That is enforced by model
validators, not by convention.

---

## `FinancialFact`

One number, at one period, from one filing.

| Field | Notes |
|---|---|
| `fact_id` | `fact:<TICKER>:<metric>:<period>[:<suffix>]`, stable across runs |
| `company_id` | ticker |
| `metric` | canonical name (`revenue`), **not** the XBRL tag |
| `xbrl_concept` | the tag that actually matched — tags vary, so record the winner |
| `value` | **always full units** |
| `unit`, `currency` | |
| `scale` | what the filing reported (`"millions"`). **Provenance only** — `value` is already normalized |
| `period_type` | `duration` or `instant` |
| `period_start` | required for `duration`, must be null for `instant` |
| `period_end`, `fiscal_period` | |
| `dimension` | segment axes, or `null` for the consolidated total |
| `filing_type`, `accession_number`, `filed_at` | |
| `retrieved_at` | always required |
| `source_url`, `source_location` | |
| `source_kind` | `xbrl_reported` / `derived` / `filing_text` / `market_api` / `estimate` |
| `derivation` | required **iff** `source_kind` is `derived` |
| `superseded_by` | set when a later filing restated this value |

### Rules the model enforces

- **Derived facts require a `Derivation`**, and nothing else may carry one. A
  computed number with no lineage is unverifiable.
- **Provenance depends on kind**: filing-sourced facts need an accession *and* a
  `filed_at`; market and estimate facts need a URL or location; all need
  `retrieved_at`.
- **`duration` needs a `period_start`; `instant` must not have one.**
- **Fractions are fractions**: `|value| ≤ 10` for `unit: fraction`.
- **A fact cannot supersede itself.**

### `scale` is provenance, not a multiplier

A filing reporting "5,000" in a table headed "in millions" produces a fact with
`value: 5000000000` and `scale: "millions"`. The `scale` field records what the
document said, so a reviewer can check the conversion. **No consumer may
multiply by it again.**

---

## The `ValueObject`

`FinancialFact` is the store's row type. `ValueObject` is how a number appears
inside an artifact (`Factsheet`, `Metrics`, `Verdict`).

```json
{
  "value": 0.40,
  "unit": "fraction",
  "type": "fact",
  "status": "ok",
  "source_id": null,
  "derived_from": ["financials.FY2025.gross_profit", "financials.FY2025.revenue"]
}
```

`type` drives the report's colour coding:

- `fact` — reported, or computed in code from reported values
- `estimate` — a forecast: consensus, or a scenario output
- `assumption` — a chosen constant: discount rate, terminal growth, exit multiple

### The four conditional rules

Enforced in three places — pydantic validators, the generated JSON Schema, and
`tests/contracts/test_value_rules.py`:

1. `status: ok` requires a numeric `value`
2. `status: ok` requires a `source_id` **or** a non-empty `derived_from`
3. `status: unavailable` requires `value: null` — never `0`
4. `unit: fraction` requires `|value| ≤ 10` — `0.25` means 25%, never `25`

Rule 3 is the one that matters most in practice. A missing number rendered as
`0` is indistinguishable from a real zero, and it propagates: zero revenue
produces infinite multiples and nonsensical growth rates, all of which look like
data.

---

## Filings and sections

`Filing` is one SEC submission. `FilingSection` is one structural chunk — an
Item, or a note within the financial statements.

Sections carry **character offsets** into the source document, so a quote can be
located exactly and the verifier's string match has somewhere to stand. `text`
is verbatim: nothing in this layer summarises.

Each section has two ids:

- `section_id` (`sec:<accession>:<item>`) — the repository key
- `source_id` (`src:edgar:<accession>:<item>`) — what `Evidence` cites

---

## Market data

`MarketSnapshot` bundles price, share count, debt, cash and enterprise value at
**one `as_of` instant**.

The timestamp lives on the snapshot, not on the fields, deliberately. Combining
a live price with last quarter's share count corrupts market cap and therefore
every multiple built on it — and does so silently.

---

## Sources and ids

`source_id` follows `src:<kind>:<ref>`:

| Prefix | Meaning |
|---|---|
| `src:edgar:<accession>:<item>` | filing text or XBRL |
| `src:market:<name>` | quote, peers, consensus, profile |
| `src:fred:<series>` | risk-free rate |
| `src:news:<n>` | a news item |
| `src:llm:<agent>` | an LLM-proposed assumption |
| `src:config:<name>` | a constant from `calc/config.py` |

Every `source_id` used inside a `Factsheet` must resolve in `factsheet.sources`.
The last two are legal only outside the fact sheet: an assumption is not a fact
about the company, and labelling it as one would be the whole problem.

---

## Storage

Postgres, **live mode only**. Tables mirror the contracts; see
`data/store/migrations/0001_initial.sql` for the list.

Mock mode uses fixture-backed repositories satisfying the same Protocols, so a
fresh clone runs the entire pipeline with no database, no keys and no network.

Two indexes carry the weight:

- `financial_facts (ticker, metric, period_end DESC, filed_at)` — every
  point-in-time query filters on `filed_at`
- a GIN index on `to_tsvector(filing_sections.text)` — scoped full-text search

Search is Postgres full-text, always scoped by ticker, form, item and date
([ADR 0006](adr/0006-no-naive-chunk-and-embed-rag.md)).

---

## Conventions

- **Fractions, not percents.** `0.25` is 25%.
- **Full USD.** Not thousands, not millions.
- **ISO 8601** dates (`YYYY-MM-DD`) and UTC timestamps.
- **Periods**: `FY2025`, `Q2-2026`, from the filer's own fiscal year end.
- **Tickers**: `^[A-Z]{1,5}([.-][A-Z])?$`, which is also the input allow-list.
- **`snake_case`** keys, lowercase enum values.
- **Capex is positive** meaning cash spent. **Net debt is positive** when debt
  exceeds cash. **FCF = op_cash_flow − capex.**
- **Missing is `{"value": null, "status": "unavailable"}`.** Never `0`, never
  `"N/A"`, never an omitted key.
