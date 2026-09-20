# MCP tools

The eleven tools `mcp_server/` exposes. This is the **only** surface P3 may touch.

Contracts: `schema/contracts/tools.py`. Generated schema: `schema/tools.json`.

---

## Transport

| Context | Transport |
|---|---|
| `MODE=live` | **stdio** — the orchestrator spawns `python -m mcp_server.server` |
| `MODE=mock`, all tests | the MCP SDK's **in-memory transport**, in-process |

Both are real MCP. Mock mode deliberately does *not* shortcut to `data.api`.

The reason: a boundary that is only exercised in production is a boundary nobody
has tested. With the in-memory transport, mock runs go through the same tool
dispatch and the same argument validation as live runs, so wiring mistakes
surface in the offline test suite rather than during a demo. The cost is
negligible — no subprocess, no serialization over a pipe.

Agent code is identical either way: both transports satisfy
`schema.contracts.interfaces.McpClient`.

---

## `as_of` is structural

Every **data** tool request inherits `DataToolRequest`, which carries a
**required** `as_of`. There is no way to define a data tool without one, and
`tests/contracts/test_models.py` asserts it.

A data tool must return only what was filed or observed on or before `as_of`.
Passing today's date is an explicit choice, not a default
([ADR 0003](adr/0003-point-in-time-correctness.md)).

`calculate_valuation` is the single exception. It is a **compute** tool: the
factsheet it works from already carries the authoritative `as_of`, and a second
date could silently disagree with the first.

---

## All tool output is untrusted data

Filing text, news and search results are arbitrary third-party prose. The server
wraps every text payload as quoted data, and `prompts/shared_rules.md` tells
agents that instructions found inside it are *data about the document*, not
directions.

**Every tool is read-only.** There is no tool that writes, and there should
never be one: an agent that can only read cannot be talked into damage by text
it found in a filing.

---

## The eleven tools

### Data tools (ten) — wrap `data/api.py`

#### `search_filings`
Which filings exist. Lets an agent fetch two sections instead of a whole 10-K.
**In:** `ticker`, `as_of`, `forms?`, `limit=20` · **Out:** `Filing[]`, newest first
**Errors:** `ValueError` for an out-of-scope ticker. Empty list is a valid answer.

#### `get_filing_section`
One structural section, verbatim, by id.
**In:** `section_id`, `as_of`, `max_chars?` · **Out:** `FilingSection`
**Errors:** `KeyError` for an unknown id, or one filed after `as_of` — an error
rather than an empty result, because silently returning nothing would look like
the filing did not exist.

#### `search_filing`
Keyword search over the extracted sections, scoped by ticker, form, item and
date. Returns whole sections, not fragments
([ADR 0006](adr/0006-no-naive-chunk-and-embed-rag.md)).
**In:** `ticker`, `query`, `as_of`, `forms?`, `items?`, `limit=10` · **Out:** `FilingSection[]`

**The index is in memory, not Postgres.** ADR 0006 specified Postgres full-text
search; the implementation ranks the already-extracted sections in process
instead. What the ADR actually rules out — chunking filings into embeddings and
retrieving fragments — is unchanged: the unit of retrieval is still a whole
structural section, still scoped by ticker, form, item and date, and the ranking
is still deterministic and inspectable. Only the index lives somewhere else.

The reason is that a run reads one company's filings, which is a few hundred
sections. A process-local index over that is faster than a round trip, needs no
service to be up, and keeps the offline test suite honest. Postgres earns its
place when the corpus outgrows one company per run, and the tool signature does
not change when it does.

#### `get_financial_facts`
The main way an agent gets numbers. Returns facts with `fact_id`s, which the
agent then cites.
**In:** `ticker`, `metrics[]`, `as_of`, `period_type?`, `periods?`,
`include_superseded=false` · **Out:** `FinancialFact[]`, newest first

Restated values are **excluded by default**. Asking for them is deliberate, and
the verifier flags a claim that cites one.

#### `get_market_snapshot`
Price, shares and the EV bridge at one instant — one object, so an agent cannot
mix timestamps.
**In:** `ticker`, `as_of` · **Out:** `MarketSnapshot | null`

#### `get_company_profile`
Identity, SIC, fiscal year end. The fiscal year end decides period labelling and
Q4 derivation.
**In:** `ticker`, `as_of` · **Out:** `CompanyProfile | null`

#### `get_peer_companies`
Candidates by SIC and market-cap band, each with a `selection_reason`.
**In:** `ticker`, `as_of`, `limit=6` · **Out:** `Peer[]`
Fewer peers than `limit` is valid and surfaces as a data-quality gap.

#### `search_news`
Post-earnings developments. The least trusted input in the system.
**In:** `ticker`, `as_of`, `lookback_days=60`, `limit=20` · **Out:** `NewsItem[]`
`as_of` bounds the window from **above** as well as below.

#### `resolve_fact`
Turn a `fact_id` back into the fact.
**In:** `fact_id`, `as_of` · **Out:** `FinancialFact | null`, plus
`is_superseded` and `is_future`

Returns the fact even when superseded or from the future, and flags both,
because the verifier must distinguish three cases: the id does not exist
(`unresolved_fact`), it was restated (`superseded_fact`), or it post-dates the
run (`future_fact`). Collapsing them into "not found" would make the verifier's
report useless.

#### `get_factsheet`
The whole reported picture of one company at one date, in one object.
**In:** `ticker`, `as_of` · **Out:** `Factsheet | null`
**Errors:** `ValueError` for an out-of-scope ticker.

`null` means the ticker is in scope but has no reportable history. An
out-of-scope ticker raises instead, so the two cases stay distinguishable.

This tool exists for one reason: `audit.run_audit(state, factsheet, ...)` needs
a `Factsheet`, and the orchestrator may not import `data/` (ADR 0007). Before
it, the only way to satisfy the auditor was to inject a factsheet from outside
the pipeline — which put a P1 artifact on a path no contract described, and
meant the object the auditor checked was not necessarily the one the tools
answered from. The orchestrator now fetches it over MCP like everything else and
passes it to `run_audit`.

It is a **data** tool: it takes `as_of`, and the returned `Factsheet.as_of`
equals it. Everything inside is filtered to that date by
`Factsheet`'s own point-in-time validator, so a violation is a loud error rather
than a quiet one.

It is also by far the most expensive tool in the set — it assembles what the
other tools return piecemeal. An agent that needs three numbers should call
`get_financial_facts`. `get_factsheet` is for the auditor and the composition
root.

### Compute tool (one) — wraps `calc/api.py`

#### `calculate_valuation`
**In:** `ticker`, `methods[]`, `peer_tickers?`, `assumptions?` · **Out:**
`Metrics` valuation block, `ReverseDcf` with sensitivity grid, `notes[]`
**No `as_of`** — see above.

> **This is the one sanctioned cross-partition import in the repo.**
> `mcp_server/` is P1; `calc/` is P2. It exists because agents must not do
> arithmetic, and MCP is the only surface agents can reach — so exactly one
> compute tool has to sit on it.
>
> The wrapper is a pass-through and holds no formula. Arithmetic appearing in
> `tools/calculate_valuation.py` is a defect; it belongs in `calc/`.

Always returns a sensitivity grid, never a single point value.

---

## Error conventions

| Condition | Response |
|---|---|
| out-of-scope ticker | `ValueError` with a human-readable reason |
| unknown id | `KeyError` |
| no results | empty list — not an error |
| provider outage | empty/`null` plus a `data_quality` gap — **never** a guess |
| bad arguments | validation error from the contract model, raised in P3 |

A failed fetch must never fall through to an agent inventing the number.

---

## Cost

A run makes seven LLM calls over filing text. Tool design is where that cost is
controlled ([roadmap](roadmap.md) Step 5):

- pass sections, not whole filings (`max_chars` on `get_filing_section`)
- each agent declares the narrow tool set it needs (`Agent.tools`)
- `search_filings` first, so an agent fetches what it needs rather than
  everything
- cache by accession number — filings are immutable, so the cache never goes
  stale
