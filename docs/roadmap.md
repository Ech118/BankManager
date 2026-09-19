# Roadmap

Six steps. Each has per-partition deliverables and one integration checkpoint
with a test that decides whether it is met — so "Step 3 is done" is a fact, not
an opinion.

Step 0 (this scaffold) is complete: contracts, generated schemas, ACME fixtures,
`api.py` stubs, contract tests, docs.

---

## Step 1 — First light

**P1** Ingest XBRL facts for the ACME fixtures plus one real ticker, with
point-in-time queries. EDGAR client with rate limiting and accession-keyed
cache; concept mapping; `check_scope`; `FixtureFactRepository` and
`PostgresFactRepository`; the initial migration.

**P2** MCP server skeleton serving `get_financial_facts`, `get_market_snapshot`
and `resolve_fact` from the fixture backend.
*(Server lives in `mcp_server/` — P1's directory — so this is a joint task; P2
supplies nothing but review at this step.)*

**P3** Coordinator that runs a single Financial Agent against the mock MCP.
`InMemoryMcpClient`, `agents/base.py`, prompt assembly, schema-validated output.

**Checkpoint:** the mock end-to-end run produces a `ResearchState` with one
section.
*Test:* `tests/e2e` — mock run produces a state with one section.

---

## Step 2 — Numbers that check out

**P1** YTD cash-flow differencing, Q4 derivation, restatement detection and
`superseded_by` linking.

**P2** Deterministic metrics with lineage: margins, growth, FCF and its
derivatives, balance sheet, working capital, quality flags. Scenario weight
bounding and the prior cap. The scoring rubric and consistency check.

**P3** Deterministic verifier wired in, and a minimal report rendered from the
state.

**Checkpoint:** ACME full-mock report with every number resolving.
*Test:* every number traces to a `fact_id`, and every `fact_id` resolves.

---

## Step 3 — Text, and a second opinion

**P1** Filing-section parsing on Items and notes, with character offsets.
Postgres full-text search.

**P2** Search tools and company/peer tools on the MCP surface.

**P3** Business Agent, and parallel execution of the financial/business pair.
Stdio MCP client. SSE progress events.

**Checkpoint:** one real ticker in live mode, for the Financial and Business
sections.
*Test:* `tests/e2e` — live thin slice, two sections, schema-valid.

---

## Step 4 — Valuation

**P1** Market data client, S&P baseline, news search.

**P2** `calculate_valuation`: multiples, peer and historical comparison, DCF and
reverse DCF with the sensitivity grid.

**P3** Valuation Agent, including peer justification and the expectations
reading.

**Checkpoint:** live valuation section, verified.
*Test:* the valuation section passes the deterministic checks on a real ticker.

---

## Step 5 — The full committee

**P3** Scenario Agent, Red Team, Synthesizer. S&P comparison. LLM verifier
checks. The retry loop with routing and the cap. Full fifteen-section report.
Prompt-injection test.

**P1/P2** Hardening and caching. Cost and latency measured per run. Cheaper
model for the verifier.

**Checkpoint:** full live report.
*Test:* all six agents run, the report passes audit, the disclaimer is present,
the injection test passes, and per-run cost is recorded.

---

## Step 6 — Does it work?

Evaluation across several tickers. Sensitivity output surfaced in the UI.
Backtest via `as_of`, with the anonymizer and the forward prediction log.

**P2** owns `backtest/` and `predictions/`. **P3** supplies the `redact` hook.

**Checkpoint:** a calibration chart, honestly labelled.

Two rules that are not negotiable here:

- Graded on **excess return over the index**, never absolute return.
- Below 100 tickers the chart is stamped `ILLUSTRATIVE` **in the image**.

And the demo must state which contamination defence was used — point-in-time
data, anonymization, or the forward log. The model may simply remember what
happened to these companies, and a backtest that does not address that is not
evidence.

---

## What is deliberately not on this roadmap

- **More agents.** Six is enough. Each one costs tokens, latency and a new way
  for sections to contradict each other.
- **Embeddings.** Structural parsing plus scoped keyword search is the starting
  point ([ADR 0006](adr/0006-no-naive-chunk-and-embed-rag.md)). Revisit only
  with a case where scoped search demonstrably fails.
- **More sectors.** v1 covers non-financial operating companies. Banks and REITs
  need a different valuation model, not a wider filter.
