# ResearchState

The single structured object the report is rendered from.

Source of truth: `schema/contracts/state.py`. Current `STATE_VERSION`: `1.0.0`.

---

## The principle

**The report is rendered from a structured `ResearchState` object, never from
free-form agent text.** ([ADR 0004](adr/0004-report-rendered-from-research-state.md))

Agents write `Claim`s into the section they own. The Report Generator renders
those claims deterministically. Nothing an agent types reaches the reader
without passing through a `Claim`, and every `Claim` goes through the
verification gate.

---

## `Claim`

The unit an agent is allowed to assert.

| Field | Notes |
|---|---|
| `claim_id` | `claim:<agent>:<slug>`, unique across the whole state |
| `text` | the assertion, one sentence |
| `value` | the `ValueObject` this claim is about, when it is about a number |
| `fact_ids` | facts it rests on — **required whenever a number appears** |
| `section_ids` | filing sections it rests on — required for qualitative claims |
| `evidence` | verbatim quotes the verifier string-matches |
| `derived_by` | `code` / `agent` / `filing_text` |
| `trend`, `confidence` | |
| `verification_status` | `pending` / `verified` / `failed` / `unverified` |

### No bare numbers

Two validators, and between them they are the enforcement of principle 2:

1. A claim carrying a `value` must cite at least one `fact_id`.
2. Every numeral in `text` must be backed by either a `fact_id`, or by appearing
   verbatim inside one of the claim's own evidence quotes.

Rule 2's second branch matters. "Senior notes mature in fiscal 2027" contains a
numeral that the truth layer holds no fact for — but the cited debt-note quote
contains `2027`, so the verifier's string match already covers it. A numeral
satisfying neither branch is a number the agent invented.

Spelled-out counts ("two large customers") are unaffected.

### Qualitative claims

An `agent`-derived claim with no number must cite `section_ids` or `evidence`,
so the verifier has something to check. A claim that is neither numeric nor
sourced is unfalsifiable, and unfalsifiable prose is what this architecture
exists to keep out of the report.

---

## The fourteen sections

Each records its owning agent, which is also the retry routing key.

| Section | Owner |
|---|---|
| `company` | business |
| `financials` | financial |
| `balance_sheet` | financial |
| `cash_flow` | financial |
| `earnings_quality` | financial |
| `management` | business |
| `competitive_position` | business |
| `valuation` | valuation |
| `expectations` | valuation |
| `catalysts` | business |
| `risks` | red_team |
| `scenarios` | scenario |
| `sp500_comparison` | scenario |
| `decision` | synthesizer |

Ownership is validated: a section whose `owner` disagrees with `SECTION_OWNERS`
is rejected. Retry routing depends on it, so silent reassignment would send
failures to the wrong agent.

---

## `ResearchState`

```
state_version      shape version of this object
schema_version     contract-set version
ticker, as_of      as_of is the point-in-time cutoff for the whole run
created_at, mode
sections           the fourteen above
agent_outputs      raw per-agent Analysis, kept for the UI lanes
scenario_result    set once calc.evaluate_scenarios has run
verification       set by audit.run_audit
data_quality
redacted           true when a redact hook anonymized filing text
```

`claim_id`s must be unique across all sections — duplicates would make
verification results ambiguous about which claim failed.

`redacted` is carried into the report, so a reader of a backtest run can see
that the agents worked from anonymized text.

---

## Versioning

`STATE_VERSION` tracks the shape of this object and is bumped when sections are
added or renamed, independently of `SCHEMA_VERSION`. A stored `ResearchState`
records the version it was written under, so an old state can be recognised
rather than silently misread.

---

## From state to report

`orchestrator/report/generator.py` renders a `Verdict`. Deterministic, no LLM —
the same state always produces the same report.

Rules:

- **Order**: verdict card first, then the case against, then the sections. The
  original design put the verdict after fifteen sections, which buried the
  answer.
- **Unverified claims are rendered with a marker, never dropped.** A claim that
  quietly disappeared leaves the reader unable to tell a checked report from an
  unchecked one.
- **`unavailable` renders as "unavailable"**, never `0` or a blank.
- **Numbers carry their `type` through**, so `fact`, `estimate` and `assumption`
  look different.
- **The disclaimer appears on every page.**
